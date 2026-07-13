import httpx
from typing import List, Dict, Optional
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from config import settings
from pathlib import Path
from pydantic import Field
import json

mcp = FastMCP(
    "OpenProject Management",
    log_level="ERROR"
)

class OpenProjectClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.OPENPROJECT_APIROOT,
            auth=httpx.BasicAuth("apikey", settings.OPENPROJECT_TOKEN),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=10.0,
        )

    def get_client(self):
        return self.client

    async def close(self):
        await self.client.aclose()

op_client = OpenProjectClient()


# Tools
@mcp.tool(
    name="list_project",
    description="Get the project that are active along with project name and id"
)
async def list_project() -> List[Dict]:
    http = op_client.get_client()
    response = await http.get("/api/v3/projects")
    response.raise_for_status()
    data = response.json()
    result = []
    for items in data["_embedded"]["elements"]:
        projects = {}
        projects["id"] = items.get("id", "")
        projects["identifier"] = items.get("identifier", "")
        projects["name"] = items.get("name", "")
        projects["active"] = items.get("active", "")
        projects["public"] = items.get("public", "")
        projects["created_at"] = items.get("createdAt", "")
        projects["updated_at"] = items.get("updatedAt", "")
        result.append(projects)

    file_path = Path(settings.OUTPUT_FILE)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=4)
    
    return result


@mcp.tool(
    name="get_project_workpackages",
    description="Get a project specific work packages"
)
async def list_project_workpackages(project_id: int) -> List[Dict]:
    http = op_client.get_client()
    response = await http.get(f"/api/v3/projects/{project_id}/work_packages")
    response.raise_for_status()
    data = response.json()
    result = []
    for item in data["_embedded"]["elements"]:
        work_package = {}
        work_package["id"] = item.get("id", "")
        work_package["subject"] = item.get("subject", "")
        work_package["description"] = item.get("description", "")
        work_package["startDate"] = item.get("startDate", "")
        work_package["dueDate"] = item.get("dueDate", "")
        work_package["percentageDone"] = item.get("percentageDone", "")
        work_package["createdAt"] = item.get("createdAt", "")
        work_package["updatedAt"] = item.get("updatedAt", "")
        work_package["author"] = item.get("_links", "").get("author", "")
        work_package["assignee"] = item.get("_links", "").get("assignee", "")
        work_package["status"] = item.get("_links", "").get("status", "")

        result.append(work_package)
    
    return result


@mcp.tool(
        name="get_work_package_hierarchy",
        description="Fetch a parent work package along with all its children, parent links, and ancestors"
)
@mcp.tool(
    name="get_work_package_hierarchy",
    description="Fetch a parent work package along with all its children, parent links, and ancestors."
)
async def get_work_package_hierarchy(work_package_id: int) -> Dict:
    """Retrieves full parent-child relationships for a specific work package safely."""
    http = op_client.get_client()
    response = await http.get(f"/api/v3/work_packages/{work_package_id}")
    response.raise_for_status()
    data = response.json()

    links = data.get("_links") or {}

    def extract_id(link_dict: dict) -> str:
        """Safely extract ID from a HAL link dict."""
        if not isinstance(link_dict, dict):
            return ""
        href = link_dict.get("href")
        if href and isinstance(href, str):
            return href.rsplit("/", 1)[-1]
        return ""

    # Extract children safely
    children = []
    for child in links.get("children") or []:
        if isinstance(child, dict):
            children.append({
                "id": extract_id(child),
                "title": child.get("title", "")
            })

    # Extract ancestors safely
    ancestors = []
    for anc in links.get("ancestors") or []:
        if isinstance(anc, dict):
            ancestors.append({
                "id": extract_id(anc),
                "title": anc.get("title", "")
            })

    # Extract direct parent safely
    parent_link = links.get("parent") or {}
    parent = None
    if parent_link.get("href"):
        parent = {
            "id": extract_id(parent_link),
            "title": parent_link.get("title", "")
        }

    status_link = links.get("status") or {}
    assignee_link = links.get("assignee") or {}

    return {
        "id": data.get("id"),
        "subject": data.get("subject", ""),
        "status": status_link.get("title", ""),
        "assignee": assignee_link.get("title", ""),
        "parent": parent,
        "ancestors": ancestors,
        "children": children,
    }


@mcp.tool(
    name="get_project_summary",
    description="Get an executive summary of a project including work package status counts and upcoming deadlines."
)
async def get_project_summary(project_id: int) -> Dict:
    """Aggregates active work packages into status counts and key details."""
    http = op_client.get_client()
    response = await http.get(f"/api/v3/projects/{project_id}/work_packages")
    response.raise_for_status()
    data = response.json()

    elements = data.get("_embedded", {}).get("elements", [])
    
    status_counts = {}
    upcoming_deadlines = []

    for item in elements:
        # Tally statuses
        status_name = item.get("_links", {}).get("status", {}).get("title", "Unknown")
        status_counts[status_name] = status_counts.get(status_name, 0) + 1
        
        # Track due dates
        due_date = item.get("dueDate") or item.get("derivedDueDate")
        if due_date:
            upcoming_deadlines.append({
                "id": item.get("id"),
                "subject": item.get("subject"),
                "dueDate": due_date,
                "status": status_name,
                "assignee": item.get("_links", {}).get("assignee", {}).get("title", "Unassigned")
            })

    # Sort deadlines ascending
    upcoming_deadlines.sort(key=lambda x: x["dueDate"])

    return {
        "projectId": project_id,
        "totalWorkPackages": data.get("total", len(elements)),
        "statusBreakdown": status_counts,
        "upcomingDeadlines": upcoming_deadlines[:10]
    }

# TODO: Check if this is needed or adding value
# @mcp.tool(
#     name="get_work_package_dependencies",
#     description="Fetch predecessor and successor relations (follows/precedes) for a specific work package or all relations."
# )
# async def get_work_package_dependencies(work_package_id: Optional[int] = None) -> List[Dict]:
#     """Retrieves relation dependencies. If work_package_id is provided, filters for that specific package."""
#     http = op_client.get_client()
    
#     url = "/api/v3/relations"
#     if work_package_id:
#         filters = json.dumps([{"involved": {"operator": "=", "values": [str(work_package_id)]}}])
#         url = f"/api/v3/relations?filters={filters}"

#     response = await http.get(url)
#     response.raise_for_status()
#     data = response.json()

#     relations = []
#     for item in data.get("_embedded", {}).get("elements", []):
#         links = item.get("_links", {})
#         relations.append({
#             "id": item.get("id"),
#             "relationType": item.get("type"),         # e.g., 'follows'
#             "reverseType": item.get("reverseType"),  # e.g., 'precedes'
#             "fromWorkPackage": {
#                 "id": links.get("from", {}).get("href", "").split("/")[-1],
#                 "title": links.get("from", {}).get("title", "")
#             },
#             "toWorkPackage": {
#                 "id": links.get("to", {}).get("href", "").split("/")[-1],
#                 "title": links.get("to", {}).get("title", "")
#             },
#             "description": item.get("description")
#         })

#     return relations

# TODO: Fix is needed for this tool
# @mcp.tool(
#     name="search_work_packages",
#     description="Search and filter work packages across projects by status name, assignee name, or subject substring."
# )
# async def search_work_packages(
#     query: Optional[str] = None,
#     assignee_name: Optional[str] = None,
#     status_name: Optional[str] = None
# ) -> List[Dict]:
#     """Filters work packages across the instance based on simple criteria."""
#     http = op_client.get_client()
    
#     # Fetch global work package list
#     response = await http.get("/api/v3/work_packages?pageSize=50")
#     response.raise_for_status()
#     data = response.json()

#     results = []
#     for item in data.get("_embedded", {}).get("elements", []):
#         links = item.get("_links", {})
        
#         subject = item.get("subject", "")
#         assignee = links.get("assignee", {}).get("title", "")
#         status = links.get("status", {}).get("title", "")

#         # Apply simple Python filters
#         if query and query.lower() not in subject.lower():
#             continue
#         if assignee_name and assignee_name.lower() not in assignee.lower():
#             continue
#         if status_name and status_name.lower() not in status.lower():
#             continue

#         results.append({
#             "id": item.get("id"),
#             "subject": subject,
#             "status": status,
#             "assignee": assignee,
#             "project": links.get("project", {}).get("title", ""),
#             "startDate": item.get("startDate") or item.get("derivedStartDate"),
#             "dueDate": item.get("dueDate") or item.get("derivedDueDate"),
#         })

#     return results

#TODO: Fix is needed for this tool
# @mcp.tool(
#     name="get_time_entries_summary",
#     description="Fetch time entries logged across work packages or for a specific work package."
# )
# async def get_time_entries_summary(work_package_id: Optional[int] = None) -> List[Dict]:
#     """Retrieves logged time entries including hours, user, and comments."""
#     http = op_client.get_client()

#     url = "/api/v3/time_entries"
#     if work_package_id:
#         filters = json.dumps([{"work_package_id": {"operator": "=", "values": [str(work_package_id)]}}])
#         url = f"/api/v3/time_entries?filters={filters}"

#     response = await http.get(url)
#     response.raise_for_status()
#     data = response.json()

#     entries = []
#     for item in data.get("_embedded", {}).get("elements", []):
#         links = item.get("_links", {})
#         comment_raw = item.get("comment", {})
        
#         entries.append({
#             "id": item.get("id"),
#             "hours": item.get("hours"),
#             "spentOn": item.get("spentOn"),
#             "user": links.get("user", {}).get("title", ""),
#             "workPackage": {
#                 "id": links.get("workPackage", {}).get("href", "").split("/")[-1],
#                 "title": links.get("workPackage", {}).get("title", "")
#             },
#             "activity": links.get("activity", {}).get("title", ""),
#             "comment": comment_raw.get("raw") if isinstance(comment_raw, dict) else str(comment_raw)
#         })

#     return entries


# Resource (Static)
@mcp.resource(
    uri="openproject://outputs/project-details",
    name="Cached Project Details",
    description="Returns the locally saved project details JSON output.",
    mime_type="application/json"
)
async def get_project_detail() -> str:
    file_path = settings.OUTPUT_DIR / "project_details.json"
    if not file_path.exists():
        return json.dumps({"error": "File not found"})
    return file_path.read_text(encoding="utf-8")


@mcp.resource(
    uri="openproject://projects/active",
    name="Active Projects List",
    description="Fetches and returns the current active OpenProject projects.",
    mime_type="application/json"
)
async def get_active_projects_resource() -> str:
    http = op_client.get_client()
    response = await http.get("/api/v3/projects")
    response.raise_for_status()
    data = response.json()

    projects = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "identifier": item.get("identifier"),
            "active": item.get("active")
        }
        for item in data.get("_embedded", {}).get("elements", [])
    ]
    return json.dumps(projects, indent=2)

# Resource (Template/Dynamic) 
@mcp.resource(
    uri="openproject://projects/{project_identifier}/work-packages",
    name="Project Work Packages by Name/Identifier",
    description="Returns all work packages under a project identifier or numeric ID (e.g., 'daily-updates' or '17').",
    mime_type="application/json"
)
async def get_project_wp_resource(project_identifier: str) -> str:
    http = op_client.get_client()
    
    # OpenProject API natively accepts identifier (slug) or numeric ID here!
    response = await http.get(f"/api/v3/projects/{project_identifier}/work_packages")
    response.raise_for_status()
    data = response.json()

    packages = []
    for item in data.get("_embedded", {}).get("elements", []):
        links = item.get("_links", {})
        packages.append({
            "id": item.get("id"),
            "subject": item.get("subject"),
            "status": links.get("status", {}).get("title"),
            "assignee": links.get("assignee", {}).get("title"),
            "dueDate": item.get("dueDate") or item.get("derivedDueDate")
        })

    return json.dumps({"project": project_identifier, "workPackages": packages}, indent=2)


@mcp.resource(
    uri="openproject://work-packages/{identifier_or_title}",
    name="Work Package Details by ID or Title",
    description="Returns detailed info for a work package by numeric ID or title search (e.g., '678' or 'True Claim').",
    mime_type="application/json"
)
async def get_wp_details_resource(identifier_or_title: str) -> str:
    http = op_client.get_client()
    wp_id = identifier_or_title

    # If user provided a title/subject string instead of a numeric ID, resolve it via search
    if not identifier_or_title.isdigit():
        filters = json.dumps([{"subject": {"operator": "~", "values": [identifier_or_title]}}])
        search_res = await http.get(f"/api/v3/work_packages?filters={filters}")
        search_res.raise_for_status()
        elements = search_res.json().get("_embedded", {}).get("elements", [])
        
        if not elements:
            return json.dumps({"error": f"No work package found matching title '{identifier_or_title}'"})
        
        # Take the best matching element's ID
        wp_id = str(elements[0].get("id"))

    # Fetch full WP details
    response = await http.get(f"/api/v3/work_packages/{wp_id}")
    response.raise_for_status()
    data = response.json()

    links = data.get("_links", {})
    details = {
        "id": data.get("id"),
        "subject": data.get("subject"),
        "startDate": data.get("startDate") or data.get("derivedStartDate"),
        "dueDate": data.get("dueDate") or data.get("derivedDueDate"),
        "status": links.get("status", {}).get("title"),
        "assignee": links.get("assignee", {}).get("title"),
        "author": links.get("author", {}).get("title"),
        "parent": links.get("parent", {}).get("title")
    }

    return json.dumps(details, indent=2)


@mcp.prompt(
    name="MorningStandup",
    description="Generate a daily executive standup report grouping tasks by assignee, highlighting blockers and missing deadlines."
)
async def morning_standup_prompt(
    project_identifier: str = Field(
        default="daily-updates", 
        description="The project identifier or ID to run the standup report for."
    )
) -> list[base.UserMessage]:

    prompt = f"""
    Please generate a Daily Morning Standup summary for the project: **{project_identifier}**.

    **Execution Steps:**
    1. Fetch all work packages for project '{project_identifier}'.
    2. Filter or highlight items updated or created recently.
    3. Group all work packages by **Assignee**.
    4. Flag any **Blockers**, tasks with **missing due dates**, or overdue items.
    5. Provide a clear **3-bullet Executive Summary** at the top.

    **Output Structure:**
    - ## Executive Summary (3 Bullets)
    - ## Attention Items (Overdue or Missing Due Dates)
    - ## Team Breakdown (Grouped by Assignee)
    """

    return [base.UserMessage(prompt.strip())]

if __name__ == "__main__":
    mcp.run(transport="stdio")