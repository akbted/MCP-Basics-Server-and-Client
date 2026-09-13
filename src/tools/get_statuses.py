from typing import Dict, List

from config.mcp_server_config import mcp, op_server


@mcp.tool(
    name="get_statuses",
    description=(
        "List all available work package statuses with their ids and isClosed "
        "flags. Useful for reporting and for update_work_package_status / "
        "update_work_package transitions."
    ),
)
async def get_statuses() -> Dict:
    http = op_server.get_client()
    resp = await http.get("/api/v3/statuses", params={"pageSize": 100})
    resp.raise_for_status()
    data = resp.json()
    elements = data.get("_embedded", {}).get("elements", [])
    statuses: List[Dict] = [
        {
            "id": s.get("id", 0),
            "name": s.get("name", ""),
            "isClosed": bool(s.get("isClosed", False)),
        }
        for s in elements
    ]
    statuses.sort(key=lambda s: s["id"])
    return {"total": data.get("total", len(statuses)), "statuses": statuses}