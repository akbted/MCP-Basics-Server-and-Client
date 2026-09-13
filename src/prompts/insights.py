from pydantic import Field
from mcp.server.mcpserver.prompts import base
from config.mcp_server_config import mcp


@mcp.prompt(
    name="MorningStandup",
    description="Generate a daily executive standup report grouping tasks by assignee, highlighting blockers and missing deadlines.",
)
async def morning_standup_prompt(
    project_identifier: str = Field(
        default="daily-updates",
        description="The project identifier or ID to run the standup report for.",
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


@mcp.prompt(
    name="DailyInsights",
    description="Generate a cross-project team insight digest for the executive agent.",
)
async def daily_insights_prompt(
    project_ids: str = Field(
        default="3",
        description="Comma-separated project IDs to analyze, e.g. '3,5,7'.",
    )
) -> list[base.UserMessage]:
    prompt = f"""
    Generate today's team insight digest for projects: {project_ids}.

    **Execution Steps:**
    1. For each project: call get_project_summary; record open/closed, overdue, due_soon, unassigned, undated, completion_rate.
    2. For each project: call get_project_blockers; note blocked items and their predecessors.
    3. For each project: call get_assignee_workload; note overloaded/light assignees and overdue items.
    4. Resolve assignee names to real users via get_project_members if the roster context helps.

    **Output Structure (ONE report):**
    - ## Executive Summary (3-5 bullets)
    - ## Per-Project Health (one row per project: open, overdue, due_soon, undated, completion_rate)
    - ## Blockers & Escalations
    - ## Team Workload (overloaded / at-risk / light)
    - ## Action Items (who should do what today)
    """
    return [base.UserMessage(prompt.strip())]


@mcp.prompt(
    name="ProjectHealthCheck",
    description="Assess delivery risk for a single project: overdue, due-soon, blockers, completion rate, stale items.",
)
async def project_health_check_prompt(
    project_id: int = Field(description="The numeric project ID to assess.")
) -> list[base.UserMessage]:
    prompt = f"""
    Run a delivery health check for project id {project_id}.

    **Execution Steps:**
    1. get_project_summary({project_id}) for counts and distributions.
    2. get_project_blockers({project_id}) for blocked items.
    3. get_assignee_workload({project_id}) for team distribution.
    4. get_project_members({project_id}) if roster context is useful.

    **Output Structure:**
    - ## Health Score & Risk Level (Green / Amber / Red with reason)
    - ## Key Metrics (overdue %, due_soon, undated, completion_rate)
    - ## Blockers
    - ## Top Risks & Recommended Actions
    """
    return [base.UserMessage(prompt.strip())]


@mcp.prompt(
    name="EscalationReview",
    description="Collect blocked, overdue, and unassigned items and draft a management escalation summary.",
)
async def escalation_review_prompt(
    project_ids: str = Field(
        default="3",
        description="Comma-separated project IDs to scan for escalations.",
    )
) -> list[base.UserMessage]:
    prompt = f"""
    Review projects {project_ids} for items needing escalation.

    **Execution Steps:**
    1. For each project: get_project_blockers and get_project_summary.
    2. Collect: blocked items, overdue items, open items without due dates, unassigned open items.

    **Output Structure:**
    - ## Blocked Work (item, predecessor, assignee)
    - ## Overdue / Missing Deadlines
    - ## Unassigned Work
    - ## Recommended Escalation (who/team to involve, why, urgency)
    """
    return [base.UserMessage(prompt.strip())]


@mcp.prompt(
    name="WeeklyTeamReview",
    description="Review team activity over the last N days: created/updated/closed per assignee and workload balance.",
)
async def weekly_team_review_prompt(
    project_id: int = Field(description="The numeric project ID to review."),
    days: int = Field(default=7, description="How many days of activity to include."),
) -> list[base.UserMessage]:
    prompt = f"""
    Produce a weekly team review for project {project_id} over the last {days} days.

    **Execution Steps:**
    1. get_assignee_workload({project_id}) for per-person open/closed, overdue, due_soon.
    2. get_project_workpackages(project_id={project_id}, recent_days={days}) for activity.
    3. get_project_blockers({project_id}) for blockers.

    **Output Structure:**
    - ## What Changed This Week (created / updated / closed)
    - ## Workload Balance (overloaded / light / unassigned)
    - ## Blockers & Risks
    - ## Recommended Focus for Next Week
    """
    return [base.UserMessage(prompt.strip())]