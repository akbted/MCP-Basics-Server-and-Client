import json
from typing import Dict, Optional

from config.mcp_server_config import mcp, op_server


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
    name="update_work_package",
    description=(
        "Update fields of an existing work package: subject, description, assignee "
        "(by name), parent_id, start_date, due_date, percentage_done. Uses fresh "
        "lockVersion and retries on 409 conflicts. notify=False (default) avoids "
        "emailing watchers."
    ),
)
async def update_work_package(
    work_package_id: int,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    parent_id: Optional[int] = None,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    percentage_done: Optional[int] = None,
    notify: bool = False,
) -> Dict:
    http = op_server.get_client()

    wp_resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    wp_resp.raise_for_status()
    wp = wp_resp.json()

    body: Dict = {"lockVersion": wp.get("lockVersion")}
    links: Dict = {}
    if subject is not None:
        body["subject"] = subject
    if description is not None:
        body["description"] = {"raw": description}
    if assignee:
        u = await _resolve_user(http, assignee)
        if u is None:
            raise ValueError(f"Unknown user '{assignee}'")
        links["assignee"] = {"href": f"/api/v3/users/{u['id']}"}
    if parent_id:
        links["parent"] = {"href": f"/api/v3/work_packages/{parent_id}"}
    if links:
        body["_links"] = links
    if start_date is not None:
        body["startDate"] = start_date
    if due_date is not None:
        body["dueDate"] = due_date
    if percentage_done is not None:
        if not 0 <= percentage_done <= 100:
            raise ValueError("percentage_done must be between 0 and 100")
        body["percentageDone"] = percentage_done

    params = {"notify": "true" if notify else "false"}
    resp = await http.patch(
        f"/api/v3/work_packages/{work_package_id}", params=params, json=body
    )
    if resp.status_code == 409:
        fresh = (await http.get(f"/api/v3/work_packages/{work_package_id}")).json()
        body["lockVersion"] = fresh.get("lockVersion")
        resp = await http.patch(
            f"/api/v3/work_packages/{work_package_id}", params=params, json=body
        )
    if resp.status_code in (422, 403):
        raise ValueError(f"Update rejected ({resp.status_code}): {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    links_out = data.get("_links", {})
    return {
        "success": True,
        "id": data.get("id", ""),
        "subject": data.get("subject", ""),
        "status": links_out.get("status", {}).get("title", ""),
        "assignee": links_out.get("assignee", {}).get("title", "") or None,
        "start_date": data.get("startDate") or "",
        "due_date": data.get("dueDate") or "",
        "percentage_done": data.get("percentageDone") or 0,
        "updated_at": data.get("updatedAt", ""),
        "lock_version": data.get("lockVersion", ""),
    }