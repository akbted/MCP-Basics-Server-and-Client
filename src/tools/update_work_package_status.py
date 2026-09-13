from typing import Dict, Optional

from config.mcp_server_config import mcp, op_server


async def _resolve_status_id(http, name: str) -> str:
    resp = await http.get("/api/v3/statuses")
    resp.raise_for_status()
    statuses = resp.json().get("_embedded", {}).get("elements", [])
    low = name.lower()
    for s in statuses:
        if s.get("name", "").lower() == low:
            return str(s["id"])
    for s in statuses:
        if low in s.get("name", "").lower():
            return str(s["id"])
    available = [s.get("name", "") for s in statuses]
    raise ValueError(f"Unknown status '{name}'. Available statuses: {available}")


@mcp.tool(
    name="update_work_package_status",
    description=(
        "Transition a work package to a new status by name (e.g. 'In progress', "
        "'Closed') or by status_id. Handles lock conflicts (409) by re-reading the "
        "current lockVersion. notify=False (default) avoids emailing receivers."
    ),
)
async def update_work_package_status(
    work_package_id: int,
    status: Optional[str] = None,
    status_id: Optional[int] = None,
    notify: bool = False,
) -> Dict:
    if not status and status_id is None:
        raise ValueError("Provide either `status` (name) or `status_id`.")

    http = op_server.get_client()
    sid = str(status_id) if status_id is not None else await _resolve_status_id(http, status)

    wp_resp = await http.get(f"/api/v3/work_packages/{work_package_id}")
    wp_resp.raise_for_status()
    wp = wp_resp.json()

    body = {
        "lockVersion": wp.get("lockVersion"),
        "_links": {"status": {"href": f"/api/v3/statuses/{sid}"}},
    }
    params = {"notify": "true" if notify else "false"}

    resp = await http.patch(f"/api/v3/work_packages/{work_package_id}", params=params, json=body)
    if resp.status_code == 409:
        fresh = (await http.get(f"/api/v3/work_packages/{work_package_id}")).json()
        body["lockVersion"] = fresh.get("lockVersion")
        resp = await http.patch(f"/api/v3/work_packages/{work_package_id}", params=params, json=body)
    if resp.status_code in (422, 403):
        raise ValueError(f"Status transition rejected ({resp.status_code}): {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    links = data.get("_links", {})
    return {
        "success": True,
        "work_package_id": work_package_id,
        "status": links.get("status", {}).get("title", ""),
        "status_id": sid,
        "lock_version": data.get("lockVersion", ""),
        "updated_at": data.get("updatedAt", ""),
    }