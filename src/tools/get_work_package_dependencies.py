from typing import Dict, List

from config.mcp_server_config import mcp, op_server
import json


def _extract_id(href) -> str:
    if href and isinstance(href, str):
        return href.rsplit("/", 1)[-1]
    return ""


@mcp.tool(
    name="get_work_package_dependencies",
    description=(
        "Get the relations (predecessors/successors) of a work package: type, "
        "from/to work package ids and titles, plus a by-type summary. Use with "
        "get_project_blockers to understand dependency chains."
    ),
)
async def get_work_package_dependencies(work_package_id: int) -> Dict:
    http = op_server.get_client()

    wp_resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    wp_resp.raise_for_status()
    wp = wp_resp.json()

    filters = json.dumps([{"involved": {"operator": "=", "values": [str(work_package_id)]}}])
    resp = await http.get("/api/v3/relations", params={"filters": filters})

    resp.raise_for_status()
    data = resp.json()

    relations: List[Dict] = []
    by_type: Dict[str, int] = {}
    for rel in data.get("_embedded", {}).get("elements", []):
        links = rel.get("_links", {})
        rtype = rel.get("type", "")
        from_ref = links.get("from") or {}
        to_ref = links.get("to") or {}
        relations.append({
            "id": rel.get("id", ""),
            "type": rtype,
            "description": rel.get("description", ""),
            "from": {"id": _extract_id(from_ref.get("href")), "title": from_ref.get("title", "")},
            "to": {"id": _extract_id(to_ref.get("href")), "title": to_ref.get("title", "")},
        })
        by_type[rtype] = by_type.get(rtype, 0) + 1

    return {
        "work_package": {"id": work_package_id, "subject": wp.get("subject", "")},
        "total_relations": len(relations),
        "relations": relations,
        "summary": {"by_type": by_type},
    }