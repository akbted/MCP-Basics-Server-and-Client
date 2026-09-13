import json
from typing import Dict, List, Optional

from config.mcp_server_config import mcp, op_server


async def _fetch_all(http, url: str, extras: Optional[dict] = None) -> List[Dict]:
    items: List[Dict] = []
    offset = 1
    total = 0
    while True:
        resp = await http.get(
            url,
            params={"pageSize": 100, "offset": offset, **(extras or {})},
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        elements = data.get("_embedded", {}).get("elements", [])
        if not elements:
            break
        items.extend(elements)
        if total and len(items) >= total:
            break
        offset += 1
    return items


def _id(href) -> str:
    return href.rsplit("/", 1)[-1] if href and isinstance(href, str) else ""


# ----------------------------------------------------------------------
# STATIC RESOURCES  (`@`-mention targets)
# ----------------------------------------------------------------------

@mcp.resource(
    uri="openproject://projects",
    name="All Projects with IDs",
    description="Live list of all accessible OpenProject projects with id, identifier, name. Resolves @project mentions and gives ids for tools.",
    mime_type="application/json",
)
async def all_projects_resource() -> str:
    http = op_server.get_client()
    items = [
        {
            "id": p.get("id"),
            "identifier": p.get("identifier"),
            "name": p.get("name"),
            "active": p.get("active"),
            "public": p.get("public"),
        }
        for p in await _fetch_all(http, "/api/v3/projects")
    ]
    return json.dumps(items, indent=2)


@mcp.resource(
    uri="openproject://members",
    name="All Members",
    description="Live roster of OpenProject members across all projects (id, name, projects_count). Resolves @member mentions.",
    mime_type="application/json",
)
async def all_members_resource() -> str:
    http = op_server.get_client()
    members: Dict[str, Dict] = {}
    for m in await _fetch_all(http, "/api/v3/memberships"):
        principal = m.get("_links", {}).get("principal") or {}
        if not isinstance(principal, dict):
            continue
        uid = _id(principal.get("href"))
        if not uid:
            continue
        rec = members.setdefault(uid, {"id": uid, "name": principal.get("title", ""), "projects_count": 0})
        rec["projects_count"] += 1
    listing = sorted(members.values(), key=lambda x: x["projects_count"], reverse=True)
    return json.dumps(listing, indent=2)


# ----------------------------------------------------------------------
# TEMPLATE / DYNAMIC RESOURCES
# ----------------------------------------------------------------------

@mcp.resource(
    uri="openproject://projects/{project_id}",
    name="Project Detail by ID",
    description="Single project detail by numeric ID or identifier (e.g. '3' or 'arca-true-claim').",
    mime_type="application/json",
)
async def project_detail_resource(project_id: str) -> str:
    http = op_server.get_client()
    resp = await http.get(f"/api/v3/projects/{project_id}")
    resp.raise_for_status()
    p = resp.json()
    return json.dumps({
        "id": p.get("id"),
        "identifier": p.get("identifier"),
        "name": p.get("name"),
        "active": p.get("active"),
        "public": p.get("public"),
        "description": (p.get("description") or {}).get("raw", ""),
    }, indent=2)


@mcp.resource(
    uri="openproject://projects/{project_id}/members",
    name="Project Members with Roles",
    description="Members of a single project (id, name, roles).",
    mime_type="application/json",
)
async def project_members_resource(project_id: str) -> str:
    http = op_server.get_client()
    filters = json.dumps([{"project": {"operator": "=", "values": [project_id]}}])
    members = []
    for m in await _fetch_all(http, "/api/v3/memberships", {"filters": filters}):
        principal = m.get("_links", {}).get("principal") or {}
        if not isinstance(principal, dict):
            continue
        members.append({
            "id": _id(principal.get("href")),
            "name": principal.get("title", ""),
            "roles": [r.get("title", "") for r in (m.get("_links", {}).get("roles") or [])],
        })
    return json.dumps(members, indent=2)


@mcp.resource(
    uri="openproject://projects/{project_identifier}/work-packages",
    name="Project Work Packages by Name/Identifier",
    description="Returns all work packages under a project identifier or numeric ID (e.g., 'daily-updates' or '17').",
    mime_type="application/json",
)
async def project_workpackages_resource(project_identifier: str) -> str:
    http = op_server.get_client()
    items = []
    for item in await _fetch_all(http, f"/api/v3/projects/{project_identifier}/work_packages"):
        links = item.get("_links", {})
        items.append({
            "id": item.get("id"),
            "subject": item.get("subject"),
            "status": links.get("status", {}).get("title"),
            "assignee": links.get("assignee", {}).get("title"),
            "dueDate": item.get("dueDate") or item.get("derivedDueDate"),
        })
    return json.dumps({"project": project_identifier, "workPackages": items}, indent=2)


@mcp.resource(
    uri="openproject://work-packages/{identifier_or_title}",
    name="Work Package Details by ID or Title",
    description="Returns detailed info for a work package by numeric ID or title search (e.g., '678' or 'True Claim').",
    mime_type="application/json",
)
async def workpackage_detail_resource(identifier_or_title: str) -> str:
    http = op_server.get_client()
    if identifier_or_title.isdigit():
        wp_id = identifier_or_title
    else:
        filters = json.dumps([{"subject": {"operator": "~", "values": [identifier_or_title]}}])
        search = await http.get("/api/v3/work_packages", params={"filters": filters})
        search.raise_for_status()
        elements = search.json().get("_embedded", {}).get("elements", [])
        if not elements:
            return json.dumps({"error": f"No work package found matching title '{identifier_or_title}'"})
        wp_id = str(elements[0].get("id"))

    response = await http.get(f"/api/v3/work_packages/{wp_id}")
    response.raise_for_status()
    data = response.json()
    links = data.get("_links", {})
    return json.dumps({
        "id": data.get("id"),
        "subject": data.get("subject"),
        "startDate": data.get("startDate") or data.get("derivedStartDate"),
        "dueDate": data.get("dueDate") or data.get("derivedDueDate"),
        "status": links.get("status", {}).get("title"),
        "assignee": links.get("assignee", {}).get("title"),
        "author": links.get("author", {}).get("title"),
        "parent": links.get("parent", {}).get("title"),
    }, indent=2)