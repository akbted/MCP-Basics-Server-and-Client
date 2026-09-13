from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Set

from config.mcp_server_config import mcp, op_server

ATTENTION_LIMIT = 10
ACTIVITY_WINDOW_DAYS = 7
DUE_SOON_DAYS = 7


def extract_workpackage(item: Dict) -> Dict:
    links = item.get("_links", {})
    due_date = item.get("dueDate") or item.get("derivedDueDate")
    start_date = item.get("startDate") or item.get("derivedStartDate")

    return {
        "id": item.get("id", ""),
        "subject": item.get("subject", ""),
        "status": links.get("status", {}).get("title", ""),
        "priority": links.get("priority", {}).get("title", ""),
        "author": links.get("author", {}).get("title", ""),
        "assignee": links.get("assignee", {}).get("title", ""),
        "progress": item.get("percentageDone") or 0,
        "start_date": start_date or "",
        "due_date": due_date or "",
        "created_at": item.get("createdAt", ""),
        "updated_at": item.get("updatedAt", ""),
        "is_overdue": _is_overdue(due_date),
    }


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


def _is_overdue(value: Optional[str]) -> bool:
    dt = _parse_dt(value)
    return bool(dt) and dt.date() < date.today()


def _is_due_soon(value: Optional[str], within_days: int = DUE_SOON_DAYS) -> bool:
    dt = _parse_dt(value)
    if dt is None:
        return False
    today = date.today()
    return today <= dt.date() <= today + timedelta(days=within_days)


def _is_recent(value: Optional[str], within_days: int = ACTIVITY_WINDOW_DAYS) -> bool:
    dt = _normalize(value)
    if dt is None:
        return False
    return dt >= datetime.now(timezone.utc) - timedelta(days=within_days)


async def _fetch_closed_statuses(http) -> Set[str]:
    try:
        resp = await http.get("/api/v3/statuses")
        resp.raise_for_status()
        statuses = resp.json().get("_embedded", {}).get("elements", [])
        return {s["name"] for s in statuses if s.get("isClosed", False)}
    except Exception:
        return {"Closed", "Done", "Cancelled", "Canceled", "Resolved", "Archived"}


def _attention_item(wp: Dict) -> Dict:
    return {
        "id": wp["id"],
        "subject": wp["subject"],
        "status": wp["status"],
        "priority": wp["priority"],
        "assignee": wp["assignee"],
        "due_date": wp["due_date"],
    }


def _no_date_item(wp: Dict) -> Dict:
    return {
        "id": wp["id"],
        "subject": wp["subject"],
        "status": wp["status"],
        "priority": wp["priority"],
        "assignee": wp["assignee"],
    }


def _activity_item(wp: Dict) -> Dict:
    return {
        "id": wp["id"],
        "subject": wp["subject"],
        "status": wp["status"],
        "assignee": wp["assignee"],
        "updated_at": wp["updated_at"],
    }


@mcp.tool(
    name="get_project_summary",
    description=(
        "Get an executive summary of a project: total/open/closed/overdue counts, "
        "status/priority/assignee distributions, attention items (overdue, due soon, "
        "unassigned, no due date), recent activity, and upcoming deadlines."
    ),
)
async def get_project_summary(project_id: int) -> Dict:
    http = op_server.get_client()

    closed_statuses = await _fetch_closed_statuses(http)

    page_size = 1000
    offset = 1
    total = 0
    all_items: List[Dict] = []

    while True:
        resp = await http.get(
            f"/api/v3/projects/{project_id}/work_packages",
            params={"pageSize": page_size, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        all_items.extend(elements)
        if len(all_items) >= total:
            break
        offset += 1

    work_packages = [extract_workpackage(item) for item in all_items]
    today = date.today()
    progress_sum = 0

    by_status: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    by_assignee: Dict[str, int] = {}
    by_author: Dict[str, int] = {}
    overdue_list: List[Dict] = []
    due_soon_list: List[Dict] = []
    unassigned_list: List[Dict] = []
    no_due_date_list: List[Dict] = []
    recent_count = 0
    recent_items: List[Dict] = []
    future_deadlines: List[Dict] = []

    for wp in work_packages:
        status = wp["status"] or "Unknown"
        assignee = wp["assignee"] or "Unassigned"
        priority = wp["priority"] or "Unknown"
        author = wp["author"] or "Unknown"

        by_status[status] = by_status.get(status, 0) + 1
        by_assignee[assignee] = by_assignee.get(assignee, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_author[author] = by_author.get(author, 0) + 1

        progress_sum += wp["progress"]

        if wp["is_overdue"]:
            overdue_list.append(wp)
        elif _is_due_soon(wp["due_date"]):
            due_soon_list.append(wp)

        is_closed = status in closed_statuses
        if not is_closed:
            if wp["assignee"] == "":
                unassigned_list.append(wp)
            if not wp["due_date"]:
                no_due_date_list.append(wp)

        if _is_recent(wp["updated_at"]):
            recent_count += 1
            if len(recent_items) < ATTENTION_LIMIT:
                recent_items.append(wp)

        due_dt = _parse_dt(wp["due_date"])
        if due_dt and due_dt.date() > today + timedelta(days=DUE_SOON_DAYS):
            future_deadlines.append(wp)

    overdue_list.sort(key=lambda wp: _parse_dt(wp["due_date"]) or datetime.min)
    due_soon_list.sort(key=lambda wp: _parse_dt(wp["due_date"]) or datetime.max)
    future_deadlines.sort(key=lambda wp: _parse_dt(wp["due_date"]) or datetime.max)
    no_due_date_list.sort(key=lambda wp: wp["updated_at"] or "", reverse=True)
    unassigned_list.sort(key=lambda wp: wp["priority"], reverse=True)

    total_wp = len(work_packages)
    closed_count = sum(1 for wp in work_packages if wp["status"] in closed_statuses)
    open_count = total_wp - closed_count
    completion_rate = round(progress_sum / total_wp, 1) if total_wp else 0.0

    return {
        "project_id": project_id,
        "total": total or total_wp,
        "open": open_count,
        "closed": closed_count,
        "overdue": len(overdue_list),
        "due_soon": len(due_soon_list),
        "unassigned": len(unassigned_list),
        "undated": len(no_due_date_list),
        "completion_rate": completion_rate,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_assignee": by_assignee,
        "by_author": by_author,
        "attention": {
            "overdue": [_attention_item(wp) for wp in overdue_list[:ATTENTION_LIMIT]],
            "due_soon": [_attention_item(wp) for wp in due_soon_list[:ATTENTION_LIMIT]],
            "unassigned": [_no_date_item(wp) for wp in unassigned_list[:ATTENTION_LIMIT]],
            "no_due_date": [_no_date_item(wp) for wp in no_due_date_list[:ATTENTION_LIMIT]],
        },
        "recent_activity": {
            "count": recent_count,
            "items": [_activity_item(wp) for wp in recent_items],
        },
        "upcoming_deadlines": [_attention_item(wp) for wp in future_deadlines[:ATTENTION_LIMIT]],
    }