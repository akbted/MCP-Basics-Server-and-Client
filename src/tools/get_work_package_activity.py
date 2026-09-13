from datetime import datetime, timezone, timedelta
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


def _normalize(value: Optional[str]) -> Optional[datetime]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@mcp.tool(
    name="get_work_package_activity",
    description=(
        "Get the activity/journal of a work package: comments, changes, users, and "
        "timestamps, newest first. Useful for judging how recently an item was "
        "actually worked on and what happened."
    ),
)
async def get_work_package_activity(work_package_id: int, limit: int = 20) -> Dict:
    http = op_server.get_client()

    wp_resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    wp_resp.raise_for_status()
    wp = wp_resp.json()

    activities: List[Dict] = []
    offset = 1
    total = 0
    while True:
        resp = await http.get(
            f"/api/v3/work_packages/{work_package_id}/activities",
            params={"pageSize": 100, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        for act in elements:
            links = act.get("_links", {})
            activities.append({
                "id": act.get("id", ""),
                "version": act.get("version", ""),
                "user": links.get("user", {}).get("title", ""),
                "comment": act.get("comment", {}).get("raw", ""),
                "details": [
                    d.get("raw", "") for d in (act.get("details") or [])
                ],
                "created_at": act.get("createdAt", ""),
            })
        if total and len(activities) >= total:
            break
        offset += 1

    activities.sort(key=lambda a: _normalize(a["created_at"]) or datetime.min, reverse=True)
    items = activities[:max(limit, 0)]

    latest = items[0]["created_at"].replace("Z", "+00:00") if items else ""
    latest_dt = _normalize(latest)
    days_since = (
        (datetime.now(timezone.utc) - latest_dt).days if latest_dt else None
    )

    return {
        "work_package": {"id": work_package_id, "subject": wp.get("subject", "")},
        "total": total,
        "latest_activity_at": latest,
        "days_since_last_activity": days_since,
        "activities": items,
    }