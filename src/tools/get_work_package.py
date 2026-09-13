from datetime import date, datetime
from typing import Dict, Optional

from config.mcp_server_config import mcp, op_server


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _is_overdue(value: Optional[str]) -> bool:
    dt = _parse_dt(value)
    return bool(dt) and dt.date() < date.today()


@mcp.tool(
    name="get_work_package",
    description=(
        "Get full details of a single work package by id: subject, type, status, "
        "priority, assignee, author, parent, dates, effort, progress, and lock "
        "version (needed for updates)."
    ),
)
async def get_work_package(work_package_id: int) -> Dict:
    http = op_server.get_client()
    resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    resp.raise_for_status()
    w = resp.json()
    links = w.get("_links", {})
    due_date = w.get("dueDate") or w.get("derivedDueDate")
    return {
        "id": w.get("id"),
        "subject": w.get("subject", ""),
        "description": (w.get("description") or {}).get("raw", ""),
        "type": links.get("type", {}).get("title", ""),
        "status": links.get("status", {}).get("title", ""),
        "priority": links.get("priority", {}).get("title", ""),
        "assignee": links.get("assignee", {}).get("title", "") or None,
        "author": links.get("author", {}).get("title", ""),
        "parent": links.get("parent", {}).get("title", "") or None,
        "project": links.get("project", {}).get("title", ""),
        "version": links.get("version", {}).get("title", "") or None,
        "start_date": w.get("startDate") or w.get("derivedStartDate"),
        "due_date": due_date,
        "is_overdue": _is_overdue(due_date),
        "estimated_time": w.get("estimatedTime") or "",
        "spent_time": w.get("spentTime") or "",
        "percentage_done": w.get("percentageDone") or 0,
        "created_at": w.get("createdAt", ""),
        "updated_at": w.get("updatedAt", ""),
        "lock_version": w.get("lockVersion"),
    }