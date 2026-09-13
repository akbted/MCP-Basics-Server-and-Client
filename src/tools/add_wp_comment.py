from typing import Dict

from config.mcp_server_config import mcp, op_server


@mcp.tool(
    name="add_wp_comment",
    description=(
        "Add a comment to a work package's activity journal. notify=False (default) "
        "postpones email notifications to receivers; set notify=True to notify them."
    ),
)
async def add_wp_comment(
    work_package_id: int,
    comment: str,
    notify: bool = False,
) -> Dict:
    if not comment or not comment.strip():
        raise ValueError("comment is required")

    http = op_server.get_client()
    resp = await http.post(
        f"/api/v3/work_packages/{work_package_id}/activities",
        params={"notify": "true" if notify else "false"},
        json={"comment": {"raw": comment}},
    )
    resp.raise_for_status()
    data = resp.json()
    links = data.get("_links", {})

    return {
        "success": True,
        "work_package_id": work_package_id,
        "activity_id": data.get("id", ""),
        "version": data.get("version", ""),
        "user": links.get("user", {}).get("title", ""),
        "comment": data.get("comment", {}).get("raw", ""),
        "created_at": data.get("createdAt", ""),
    }