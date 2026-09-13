import json
from typing import Dict, List

from config.mcp_server_config import mcp, op_server


def _extract_id(href) -> str:
    if href and isinstance(href, str):
        return href.rsplit("/", 1)[-1]
    return ""


@mcp.tool(
    name="get_project_members",
    description=(
        "Get all members of a project with their user id, name, and roles. Use this "
        "to resolve assignee/candidate names to real OpenProject users."
    ),
)
async def get_project_members(project_id: int) -> Dict:
    http = op_server.get_client()
    filters = json.dumps([{"project": {"operator": "=", "values": [str(project_id)]}}])

    members: List[Dict] = []
    offset = 1
    total = 0
    while True:
        resp = await http.get(
            "/api/v3/memberships",
            params={"pageSize": 100, "offset": offset, "filters": filters},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        for item in elements:
            links = item.get("_links", {})
            principal = links.get("principal") or {}
            if not isinstance(principal, dict):
                principal = {}
            role_titles = [
                r.get("title", "")
                for r in (links.get("roles") or [])
                if isinstance(r, dict)
            ]
            members.append({
                "id": _extract_id(principal.get("href")),
                "name": principal.get("title", ""),
                "membership_id": item.get("id", ""),
                "roles": role_titles,
                "href": principal.get("href", ""),
            })
        if total and len(members) >= total:
            break
        offset += 1

    members.sort(key=lambda m: m["name"].lower())

    by_role: Dict[str, int] = {}
    for m in members:
        for role in m["roles"]:
            by_role[role] = by_role.get(role, 0) + 1

    return {
        "project_id": project_id,
        "total": len(members),
        "members": members,
        "by_role": by_role,
    }