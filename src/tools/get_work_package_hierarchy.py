import json
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional

from config.mcp_server_config import mcp, op_server

DATE_FIELDS = {"created_at", "updated_at", "start_date", "due_date"}


def extract_workpackage(item: Dict, include_description: bool = False) -> Dict:
    links = item.get("_links", {})
    due_date = item.get("dueDate") or item.get("derivedDueDate")
    start_date = item.get("startDate") or item.get("derivedStartDate")

    return {
        "id": item.get("id", ""),
        "subject": item.get("subject", ""),
        "description": item.get("description", "") if include_description else "",
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


def _matches(value: str, term: Optional[str]) -> bool:
    return term is None or term.lower() in value.lower()


def _client_matches(
    wp: Dict,
    assignee: Optional[str],
    author: Optional[str],
    status: Optional[str],
    priority: Optional[str],
) -> bool:
    return (
        _matches(wp["assignee"], assignee)
        and _matches(wp["author"], author)
        and _matches(wp["status"], status)
        and _matches(wp["priority"], priority)
    )


def _build_children_filters(
    work_package_id: int,
    date_field: str,
    from_date: Optional[str],
    to_date: Optional[str],
    recent_days: Optional[int],
) -> str:
    filters = [{"parent": {"operator": "=", "values": [str(work_package_id)]}}]
    lo, hi = from_date, to_date
    if recent_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date().isoformat()
        lo = lo if lo is not None else cutoff
    if lo:
        filters.append({date_field: {"operator": ">=", "values": [lo]}})
    if hi:
        filters.append({date_field: {"operator": "<=", "values": [hi]}})
    return json.dumps(filters)


def build_summary(wps: List[Dict]) -> Dict:
    by_status, by_assignee, by_priority, by_author = {}, {}, {}, {}
    overdue = 0
    open_count = 0
    closed_hint = ("closed", "done", "cancelled", "canceled", "resolved", "archived")
    for wp in wps:
        status = wp["status"] or "Unknown"
        assignee = wp["assignee"] or "Unassigned"
        priority = wp["priority"] or "Unknown"
        author = wp["author"] or "Unknown"
        by_status[status] = by_status.get(status, 0) + 1
        by_assignee[assignee] = by_assignee.get(assignee, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_author[author] = by_author.get(author, 0) + 1
        if wp["is_overdue"]:
            overdue += 1
        if not any(h in status.lower() for h in closed_hint):
            open_count += 1
    return {
        "by_status": by_status,
        "by_assignee": by_assignee,
        "by_priority": by_priority,
        "by_author": by_author,
        "open": open_count,
        "overdue": overdue,
    }


def _extract_id(href: Optional[str]) -> str:
    if href and isinstance(href, str):
        return href.rsplit("/", 1)[-1]
    return ""


@mcp.tool(
    name="get_work_package_hierarchy",
    description=(
        "Fetch a work package with its parent, ancestors, and children. Children can be "
        "filtered by assignee, author, status, priority, and date range, and are capped at "
        "`limit` rows (default 50; None = all). Returns a structured hierarchy with a "
        "children summary. Use summary_only=True for aggregates only."
    ),
)
async def get_work_package_hierarchy(
    work_package_id: int,
    assignee: Optional[str] = None,
    author: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    date_field: str = "created_at",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    recent_days: Optional[int] = None,
    group_by: Optional[str] = None,
    limit: Optional[int] = 50,
    include_description: bool = False,
    summary_only: bool = False,
) -> Dict:
    if date_field not in DATE_FIELDS:
        raise ValueError(f"date_field must be one of {sorted(DATE_FIELDS)}, got '{date_field}'")

    http = op_server.get_client()

    root_resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    root_resp.raise_for_status()
    root = root_resp.json()
    links = root.get("_links", {})

    parent = None
    parent_href = links.get("parent", {}).get("href")
    if parent_href:
        parent_id = _extract_id(parent_href)
        if parent_id:
            parent_resp = await http.get(f"/api/v3/work_packages/{parent_id}")
            parent_resp.raise_for_status()
            parent = extract_workpackage(parent_resp.json(), include_description=include_description)

    ancestors = []
    for anc in links.get("ancestors") or []:
        if isinstance(anc, dict):
            ancestors.append({"id": _extract_id(anc.get("href")), "title": anc.get("title", "")})

    filters = _build_children_filters(
        work_package_id, date_field, from_date, to_date, recent_days
    )
    page_size = max(limit or 100, 100)
    offset = 1
    total = 0
    scanned = 0
    children: List[Dict] = []
    truncated = False

    while True:
        resp = await http.get(
            "/api/v3/work_packages",
            params={"pageSize": page_size, "offset": offset, "filters": filters},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break

        scanned += len(elements)
        for item in elements:
            wp = extract_workpackage(item, include_description=include_description)
            if _client_matches(wp, assignee, author, status, priority):
                children.append(wp)

        if limit is not None and len(children) >= limit:
            children = children[:limit]
            truncated = True
            break
        if scanned >= total:
            break
        offset += 1

    children.sort(key=lambda wp: _normalize(wp["created_at"]) or datetime.min, reverse=True)

    filters_applied: Dict = {"limit": limit, "include_description": include_description, "summary_only": summary_only}
    for key, val in (("assignee", assignee), ("author", author), ("status", status), ("priority", priority)):
        if val is not None:
            filters_applied[key] = val
    if from_date is not None or to_date is not None or recent_days is not None:
        filters_applied["date_field"] = date_field
        filters_applied["from_date"] = from_date
        filters_applied["to_date"] = to_date
        filters_applied["recent_days"] = recent_days

    children_block: Dict = {
        "total": total,
        "matched": len(children),
        "truncated": truncated,
        "filters_applied": filters_applied,
        "summary": build_summary(children),
    }

    if not summary_only:
        if group_by in ("status", "assignee", "priority", "author"):
            groups: Dict[str, List[Dict]] = {}
            for wp in children:
                key = wp.get(group_by) or "Unknown"
                groups.setdefault(key, []).append(wp)
            children_block["groups"] = {k: {"count": len(v), "items": v} for k, v in groups.items()}
        else:
            children_block["items"] = children

    return {
        "work_package_id": work_package_id,
        "work_package": extract_workpackage(root, include_description=include_description),
        "parent": parent,
        "ancestors": ancestors,
        "children": children_block,
    }