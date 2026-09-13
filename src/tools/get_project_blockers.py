import json
from typing import Dict, List, Optional, Set

from config.mcp_server_config import mcp, op_server


def extract_workpackage(item: Dict) -> Dict:
    links = item.get("_links", {})
    due_date = item.get("dueDate") or item.get("derivedDueDate")

    return {
        "id": item.get("id", ""),
        "subject": item.get("subject", ""),
        "type": links.get("type", {}).get("title", ""),
        "status": links.get("status", {}).get("title", ""),
        "priority": links.get("priority", {}).get("title", ""),
        "author": links.get("author", {}).get("title", ""),
        "assignee": links.get("assignee", {}).get("title", ""),
        "due_date": due_date or "",
        "created_at": item.get("createdAt", ""),
        "updated_at": item.get("updatedAt", ""),
    }


def _extract_id(href) -> str:
    if href and isinstance(href, str):
        return href.rsplit("/", 1)[-1]
    return ""


async def _fetch_closed_statuses(http) -> Set[str]:
    try:
        resp = await http.get("/api/v3/statuses")
        resp.raise_for_status()
        statuses = resp.json().get("_embedded", {}).get("elements", [])
        return {s["name"] for s in statuses if s.get("isClosed", False)}
    except Exception:
        return {"Closed", "Done", "Cancelled", "Canceled", "Resolved", "Archived"}


@mcp.tool(
    name="get_project_blockers",
    description=(
        "Identify blocked work packages in a project. An item is BLOCKED when it has "
        "a 'follows' relation to an OPEN predecessor. scan_limit caps how many open "
        "items have their relations checked (default 30); set scan_limit=0 to scan "
        "every open work package. include_requires_review=True lists follow-relations "
        "pointing to items outside this project (status unknown)."
    ),
)
async def get_project_blockers(
    project_id: int,
    scan_limit: int = 30,
    include_requires_review: bool = False,
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

    by_id = {wp["id"]: wp for wp in work_packages}
    open_wps = [wp for wp in work_packages if (wp["status"] or "") not in closed_statuses]

    scan_targets = open_wps if scan_limit == 0 else open_wps[: max(scan_limit, 0)]

    blocked: List[Dict] = []
    requires_review: List[Dict] = []
    seen: set = set()

    for wp in scan_targets:
        rel_resp = await http.get(f"/api/v3/work_packages/{wp['id']}/relations")
        if rel_resp.status_code != 200:
            continue
        for rel in rel_resp.json().get("_embedded", {}).get("elements", []):
            if rel.get("type") != "follows":
                continue
            links = rel.get("_links", {})
            pred_href = (links.get("to") or {}).get("href", "")
            pred_id = _extract_id(pred_href)
            pred_title = (links.get("to") or {}).get("title", "")
            pred = by_id.get(pred_id)

            entry = {
                "id": wp["id"],
                "subject": wp["subject"],
                "status": wp["status"],
                "priority": wp["priority"],
                "assignee": wp["assignee"],
                "due_date": wp["due_date"],
            }

            if pred is None:
                if include_requires_review and pred_id not in seen:
                    seen.add(pred_id)
                    requires_review.append({
                        **entry,
                        "predecessor": {"id": pred_id or "", "title": pred_title, "status": "unknown (other project)"},
                    })
                continue

            if (pred["status"] or "") in closed_statuses:
                continue

            if wp["id"] not in seen:
                seen.add(wp["id"])
                blocked.append({
                    **entry,
                    "blocked_by": {
                        "id": pred["id"],
                        "subject": pred["subject"],
                        "status": pred["status"],
                    },
                })

    return {
        "project_id": project_id,
        "total_open": len(open_wps),
        "scanned_open": len(scan_targets),
        "blocked_count": len(blocked),
        "blocked": blocked,
        "requires_review": requires_review,
    }