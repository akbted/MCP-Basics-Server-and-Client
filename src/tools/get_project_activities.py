import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.mcp_server_config import mcp, op_server


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@mcp.tool(
    name="get_project_activities",
    description=(
        "Get the most recently updated work packages across a project, newest "
        "first, within the last `days` days. Returns bounded rows (capped at "
        "`limit`). Serves as the project-scope activity feed."
    ),
)
async def get_project_activities(
    project_id: int,
    days: int = 7,
    limit: Optional[int] = 20,
) -> Dict:
    if days < 1:
        raise ValueError("days must be >= 1")
    cap = limit if limit is not None else 200
    if cap < 1:
        raise ValueError("limit must be >= 1")

    http = op_server.get_client()
    filters = json.dumps([{"updatedAt": {"operator": ">t-", "values": [str(days)]}}])
    sort_by = json.dumps([["updatedAt", "desc"]])

    items: List[Dict] = []
    offset = 1
    total = 0
    truncated = False

    while True:
        resp = await http.get(
            f"/api/v3/projects/{project_id}/work_packages",
            params={
                "pageSize": 100,
                "offset": offset,
                "filters": filters,
                "sortBy": sort_by,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        for wp in elements:
            links = wp.get("_links", {})
            updated_at = wp.get("updatedAt", "")
            dt = _parse_dt(updated_at)
            days_since = (datetime.now(timezone.utc) - dt).days if dt else None
            items.append({
                "id": wp.get("id", ""),
                "subject": wp.get("subject", ""),
                "type": links.get("type", {}).get("title", ""),
                "status": links.get("status", {}).get("title", ""),
                "assignee": links.get("assignee", {}).get("title", "") or None,
                "updated_at": updated_at,
                "days_since_update": days_since,
            })
        if len(items) >= cap:
            items = items[:cap]
            truncated = True
            break
        if len(items) >= total:
            break
        offset += 1

    return {
        "project_id": project_id,
        "days": days,
        "limit": cap,
        "total_in_window": total,
        "returned": len(items),
        "truncated": truncated,
        "activities": items,
    }