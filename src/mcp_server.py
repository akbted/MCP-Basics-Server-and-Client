import httpx
from typing import List, Dict
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


# Resource (Static)
@mcp.resource("file:///outputs/project_details.json", mime_type="application/json")
async def get_project_detail() -> Dict:
    file_path = settings.OUTPUT_DIR / "project_details.json"
    return file_path.read_text(encoding="utf-8")

@mcp.resource("file:///outputs", mime_type="application/json")
async def fetch_outputs() -> str:
    files = [f.name for f in settings.OUTPUT_DIR.glob("*") if f.is_file()]
    return json.dumps(files)

# Resource (Template/Dynamic) # TODO

@mcp.prompt(
    name = "Get Updates",
    description="Get the Latest Work Packages in order for all the projects based on updated date"
)
async def get_workpackage_order(project_details: str = Field("Input the json contents of the project_details")) -> list[base.Message]:
    prompt = f"""
    You are given project data as JSON.

    Task:
    1. Read the project details carefully.
    2. Identify all work packages across all projects.
    3. Sort the work packages by updated date in descending order (latest first).
    4. Return the result in clean markdown.
    5. Group work packages under their project name when helpful.
    6. For each work package, include key fields such as project name, work package name or ID, updated date, and status if available.
    7. If any updated date is missing or invalid, place that work package at the end and mention it clearly.
    8. Do not invent fields or values.

    Input JSON:
    <project_details_json>
    {project_details}
    </project_details_json>

    Output requirements:
    - Use markdown.
    - Use clear headers.
    - Use bullet points or tables where useful.
    - Keep the output factual and based only on the input JSON.
    - Do not explain your process.
    """
    return [base.UserMessage(prompt)]



if __name__ == "__main__":
    mcp.run(transport="stdio")