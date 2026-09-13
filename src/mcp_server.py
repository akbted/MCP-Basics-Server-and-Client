import httpx
from typing import List, Dict, Optional
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts import base
from pathlib import Path
from pydantic import Field
import json


from config.mcp_server_config import mcp
from tools.get_project_summary import get_project_summary
from tools.get_work_package_hierarchy import get_work_package_hierarchy
from tools.get_workpackages import list_project_workpackages
from tools.list_projects import list_project

from tools.get_assignee_workload import get_assignee_workload
from tools.get_project_members import get_project_members
from tools.get_work_package_activity import get_work_package_activity
from tools.get_project_blockers import get_project_blockers
from tools.get_work_package_dependencies import get_work_package_dependencies
from tools.add_wp_comment import add_wp_comment
from tools.update_work_package_status import update_work_package_status
from tools.create_work_package import create_work_package


from resources.projects import (
    all_projects_resource,
    all_members_resource,
    project_detail_resource,
    project_members_resource,
    project_workpackages_resource,
    workpackage_detail_resource,
)
from prompts.insights import (
    morning_standup_prompt,
    daily_insights_prompt,
    project_health_check_prompt,
    escalation_review_prompt,
    weekly_team_review_prompt,
)

if __name__ == "__main__":
    mcp.run(transport="stdio")