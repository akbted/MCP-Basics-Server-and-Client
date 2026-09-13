from typing import List, Dict
from config.mcp_server_config import mcp, op_server


@mcp.tool(
    name="list_project",
    description="Get the project that are active along with project name and id"
)
async def list_project() -> List[Dict]:
    http = op_server.get_client()
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

    # file_path = Path(settings.OUTPUT_FILE)
    # file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # with open(file_path, "w", encoding="utf-8") as file:
    #     json.dump(result, file, indent=4)
    
    return result