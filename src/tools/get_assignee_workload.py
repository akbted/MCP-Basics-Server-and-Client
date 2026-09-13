from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Set

from config.mcp_server_config import mcp, op_server

ATTENTION_LIMIT = 5


def extract_workpackage(item: Dict) -> Dict:
    links = item.get("_links", {})
    due_date = item.get("dueDate") or item.get("derivedDueDate")
    start_date = item.get("startDate") or item.get("derivedStartDate")

    return {
        "id": item.get("id", ""),
        "subject": item.get("subject", ""),
        "type": links.get("type", {}).get("title", ""),
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


def _is_due_soon(value: Optional[str], within_days: int = 7) -> bool:
    dt = _parse_dt(value)
    if dt is None:
        return False
    today = date.today()
    return today <= dt.date() <= today + timedelta(days=within_days)


async def _fetch_closed_statuses(http) -> Set[str]:
    try:
        resp = await http.get("/api/v3/statuses")
        resp.raise_for_status()
        statuses = resp.json().get("_embedded", {}).get("elements", [])
        return {s["name"] for s in statuses if s.get("isClosed", False)}
    except Exception:
        return {"Closed", "Done", "Cancelled", "Canceled", "Resolved", "Archived"}


def _top_item(wp: Dict) -> Dict:
    return {
        "id": wp["id"],
        "subject": wp["subject"],
        "status": wp["status"],
        "priority": wp["priority"],
        "due_date": wp["due_date"],
    }


@mcp.tool(
    name="get_assignee_workload",
    description=(
        "Get per-assignee workload for a project: open work package counts, priority "
        "breakdown, overdue, due-soon, oldest open item, and top items for each person. "
        "Unassigned items are reported separately. include_closed=True also tallies "
        "closed items per person."
    ),
)
async def get_assignee_workload(
    project_id: int,
    include_closed: bool = False,
    member_limit: Optional[int] = None,
) -> Dict:
    http = op_server.get_client()
    closed_statuses = await _fetch_closed_statuses(http)

    work_packages: List[Dict] = []
    offset = 1
    total = 0
    while True:
        resp = await http.get(
            f"/api/v3/projects/{project_id}/work_packages",
            params={"pageSize": 1000, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        work_packages.extend(extract_workpackage(item) for item in elements)
        if len(work_packages) >= total:
            break
        offset += 1

    members: Dict[str, Dict] = {}
    total_open = 0
    total_closed = 0

    for wp in work_packages:
        is_open = (wp["status"] or "") not in closed_statuses
        if not include_closed and not is_open:
            continue
        if is_open:
            total_open += 1
        else:
            total_closed += 1

        name = wp["assignee"] or "Unassigned"
        m = members.setdefault(name, {
            "open": 0,
            "closed": 0 if include_closed else 0,
            "by_priority": {},
            "overdue": 0,
            "due_soon": 0,
            "oldest_item": None,
            "_oldest_dt": None,
            "top_items": [],
        })
        m["open" if is_open else "closed"] += 1

        if is_open:
            priority = wp["priority"] or "Unknown"
            m["by_priority"][priority] = m["by_priority"].get(priority, 0) + 1
            if wp["is_overdue"]:
                m["overdue"] += 1
            if _is_due_soon(wp["due_date"]):
                m["due_soon"] += 1
            created_dt = _normalize(wp["created_at"])
            if created_dt and (m["_oldest_dt"] is None or created_dt < m["_oldest_dt"]):
                m["_oldest_dt"] = created_dt
                m["oldest_item"] = {
                    "id": wp["id"],
                    "subject": wp["subject"],
                    "created_at": wp["created_at"],
                }
            if len(m["top_items"]) < ATTENTION_LIMIT:
                m["top_items"].append(_top_item(wp))

    unassigned = members.pop("Unassigned", None)

    def _emit(name: str, m: Dict) -> Dict:
        item = {
            "name": name,
            "open": m["open"],
            "closed": m["closed"],
            "overdue": m["overdue"],
            "due_soon": m["due_soon"],
            "by_priority": m["by_priority"],
            "oldest_item": m["oldest_item"],
            "top_items": m["top_items"],
        }
        if include_closed and m["closed"]:
            item["completion_ratio"] = round(
                m["closed"] / (m["open"] + m["closed"]), 2
            ) if (m["open"] + m["closed"]) else 0.0
        return item

    sorted_members = sorted(members.items(), key=lambda kv: kv[1]["open"], reverse=True)
    if member_limit is not None:
        sorted_members = sorted_members[:member_limit]

    unassigned_block = None
    if unassigned:
        unassigned_block = _emit("Unassigned", unassigned)

    return {
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_open": total_open,
        "total_closed": total_closed,
        "member_count": len(sorted_members),
        "unassigned": unassigned_block,
        "members": [_emit(name, m) for name, m in sorted_members],
        "summary": {
            "by_assignee": {
                name: m["open"] for name, m in sorted_members
            },
        },
    }