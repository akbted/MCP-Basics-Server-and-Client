import json
from typing import Dict, Optional

from config.mcp_server_config import mcp, op_server


async def _resolve_named(http, endpoint: str, name: str) -> Optional[Dict]:
    resp = await http.get(endpoint, params={"pageSize": 1000})
    resp.raise_for_status()
    elements = resp.json().get("_embedded", {}).get("elements", [])
    low = name.lower()
    for e in elements:
        if e.get("name", "").lower() == low:
            return e
    for e in elements:
        if low in e.get("name", "").lower():
            return e
    return None


async def _resolve_user(http, name: str) -> Optional[Dict]:
    filters = json.dumps([{"name": {"operator": "~", "values": [name]}}])
    resp = await http.get("/api/v3/users", params={"pageSize": 100, "filters": filters})
    resp.raise_for_status()
    elements = resp.json().get("_embedded", {}).get("elements", [])
    for e in elements:
        if e.get("name", "").lower() == name.lower():
            return e
    return elements[0] if elements else None


@mcp.tool(
    name="create_work_package",
    description=(
        "Create a work package in a project. Required: project_id, subject. Optional: "
        "description, type_name (default 'Task'), priority, assignee (names, resolved "
        "to ids), parent_id, start_date, due_date (YYYY-MM-DD). notify=False (default) "
        "avoids emailing watchers."
    ),
)
async def create_work_package(
    project_id: int,
    subject: str,
    description: Optional[str] = None,
    type_name: Optional[str] = "Task",
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    parent_id: Optional[int] = None,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    notify: bool = False,
) -> Dict:
    if not subject or not subject.strip():
        raise ValueError("subject is required")

    http = op_server.get_client()

    links = {"project": {"href": f"/api/v3/projects/{project_id}"}}

    type_ref = await _resolve_named(http, "/api/v3/types", type_name or "Task") if type_name else None
    links["type"] = {"href": f"/api/v3/types/{type_ref['id'] if type_ref else 1}"}

    if priority:
        p = await _resolve_named(http, "/api/v3/priorities", priority)
        if p is None:
            raise ValueError(f"Unknown priority '{priority}'")
        links["priority"] = {"href": f"/api/v3/priorities/{p['id']}"}

    if assignee:
        u = await _resolve_user(http, assignee)
        if u is None:
            raise ValueError(f"Unknown user '{assignee}'")
        links["assignee"] = {"href": f"/api/v3/users/{u['id']}"}

    if parent_id:
        links["parent"] = {"href": f"/api/v3/work_packages/{parent_id}"}

    body: Dict = {"subject": subject, "_links": links}
    if description:
        body["description"] = {"raw": description}
    if start_date:
        body["startDate"] = start_date
    if due_date:
        body["dueDate"] = due_date

    resp = await http.post(
        f"/api/v3/projects/{project_id}/work_packages",
        params={"notify": "true" if notify else "false"},
        json=body,
    )
    if resp.status_code in (422, 403):
        raise ValueError(f"Create rejected ({resp.status_code}): {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    links_out = data.get("_links", {})
    return {
        "success": True,
        "id": data.get("id", ""),
        "subject": data.get("subject", ""),
        "type": links_out.get("type", {}).get("title", ""),
        "status": links_out.get("status", {}).get("title", ""),
        "priority": links_out.get("priority", {}).get("title", ""),
        "assignee": links_out.get("assignee", {}).get("title", "") or None,
        "parent_id": parent_id,
        "start_date": start_date,
        "due_date": due_date,
        "href": links_out.get("self", {}).get("href", ""),
    }