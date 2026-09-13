from typing import Dict, Union
import json

from config.mcp_server_config import mcp, op_server


@mcp.tool(
    name="get_project",
    description=(
        "Get details of a single OpenProject project by numeric id or identifier "
        "(e.g. 17 or 'daily-updates'). Optionally includes work package and member "
        "counts (single bounded count queries)."
    ),
)
async def get_project(project_id: Union[int, str], include_counts: bool = False) -> Dict:
    http = op_server.get_client()
    resp = await http.get(f"/api/v3/projects/{project_id}")
    resp.raise_for_status()
    p = resp.json()

    result = {
        "id": p.get("id"),
        "identifier": p.get("identifier", ""),
        "name": p.get("name", ""),
        "active": p.get("active"),
        "public": p.get("public"),
        "description": (p.get("description") or {}).get("raw", ""),
        "created_at": p.get("createdAt", ""),
        "updated_at": p.get("updatedAt", ""),
    }

    if include_counts:
        wp = await http.get(f"/api/v3/projects/{project_id}/work_packages", params={"pageSize": 1})
        wp.raise_for_status()
        result["work_package_count"] = wp.json().get("total", 0)
        filters = json.dumps([{"project": {"operator": "=", "values": [str(project_id)]}}])
        mb = await http.get("/api/v3/memberships", params={"pageSize": 1, "filters": filters})
        mb.raise_for_status()
        result["member_count"] = mb.json().get("total", 0)

    return result