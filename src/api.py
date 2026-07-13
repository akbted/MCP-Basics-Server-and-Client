import json
import uuid
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.memory import InMemorySaver
from mcp_client import MCPClient

from config import ROOT
from langchain_core.utils.uuid import uuid7
from config import settings


# ----------------------------------------------------------------------
# GLOBAL STATE INITIALIZATION
# ----------------------------------------------------------------------
MODEL_NAME = "nvidia/nemotron-3-super-120b-a12b:free"

llm = ChatOpenRouter(
    model=MODEL_NAME,
    api_key=settings.OPENROUTER
)

# Global instances populated inside lifespan context
mcp_client: Optional[MCPClient] = None
agent_instance: Optional[Any] = None


# ----------------------------------------------------------------------
# LIFESPAN MANAGEMENT (STARTUP & SHUTDOWN)
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles connection startup and graceful shutdown of the background
    subprocess holding standard input/output transport streams.
    """
    global mcp_client, agent_instance
    print("[MCP] Initiating connection to standard I/O sub-server...")
    
    # Instantiate the client mapping to your real local Python file server
    mcp_client = MCPClient("python", [f"{ROOT}/src/mcp_server.py"])
    await mcp_client.connect()
    
    # Retrieve the live tool bindings directly from your running subprocess
    print("[MCP] Loading active server schema tool references...")
    mcp_tools = await mcp_client.get_tools()
    
    # Initialize the actual agent run loop
    print("[Agent] Compiling agent run graph with InMemory checkpointer...")
    agent_instance = create_agent(
        model=llm,
        system_prompt="You are a helpful assistant. Be concise and accurate.",
        checkpointer=InMemorySaver(),
        tools=mcp_tools
    )
    
    print("[MCP Engine] All systems successfully initialized and ready!")
    yield
    print("[MCP Engine] Shutting down connected subprocess channels...")

# ----------------------------------------------------------------------
# FASTAPI APPLICATION SETUP
# ----------------------------------------------------------------------
app = FastAPI(
    title="Real MCP Agent Host Server",
    description="Live FastAPI server executing standard LangGraph agent models over physical subprocess contexts",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# ENDPOINTS: DYNAMIC DISCOVERY APIS FOR AUTOCOMPLETE & FRONTEND
# ----------------------------------------------------------------------
@app.get("/api/servers")
async def get_servers():
    """Retrieve connected server status."""
    return [
        {
            "id": "openproject-mcp",
            "name": "OpenProject Live Server",
            "active": mcp_client is not None,
            "uri": "stdio://mcp_server.py",
            "latency": "connected"
        }
    ]

@app.get("/api/prompts")
async def get_prompts():
    """
    Dynamically lists all prompt templates registered on the target subserver.
    """
    if not mcp_client:
        return []
    try:
        # Request dynamic list over the real standard connection session
        raw_prompts = await mcp_client.session().list_prompts()
        return [
            {"name": p.name, "desc": p.description or "Active prompt template", "content": ""}
            for p in raw_prompts
        ]
    except Exception as e:
        # Fallback to local default schemas if connection stream is idle
        return [
            {"name": "GetUpdates", "desc": "Fetches current progress updates based on project JSON metrics", "content": ""}
        ]

@app.get("/api/resources")
async def get_resources():
    """
    Dynamically lists resources from the live sub-server.
    """
    if not mcp_client:
        return []
    try:
        raw_resources = await mcp_client.session().list_resources()
        return [
            {"name": r.name, "desc": r.description or "Local data file context", "content": r.uri}
            for r in raw_resources
        ]
    except Exception as e:
        # Local fallback parameters for visual autocomplete reference
        return [
            {"name": "project_details.json", "desc": "Physical path resource file context mapping", "content": "file:///outputs/project_details.json"}
        ]

# ----------------------------------------------------------------------
# CHAT EXECUTION: THE LIVE RUNTIME CONTROLLER
# ----------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str
    thread_id: Optional[str] = None


@app.post("/api/chat")
async def process_agent_chat(payload: ChatMessage):
    """
    Parses active workspace entries, executes resource injections from standard
    file paths, runs live tool execution requests, and returns agent final output.
    """
    if not agent_instance or not mcp_client:
        raise HTTPException(status_code=500, detail="MCP Backend engine is not initialized.")

    user_text = payload.message
    messages_payload = []
    
    # Generate unique session thread id for the stateful saver checkpointer
    thread_id = payload.thread_id or str(uuid7())
    config = {"configurable": {"thread_id": thread_id}}

    detected_prompts = []
    detected_resources = []

    # 1. Parsing and Ingesting `@` Resource Contexts
    # Example: User includes '@file:///outputs/project_details.json' or '@project_details.json'
    if "@" in user_text:
        words = user_text.split()
        for word in words:
            if word.startswith("@"):
                res_target = word.replace("@", "").strip()
                # Use absolute file matching or pass straight to get_resources
                if not res_target.startswith("file://"):
                    res_target = f"file:///outputs/{res_target}"
                detected_resources.append(res_target)

    # 2. Parsing and Ingesting `/` Prompt Templates
    if "/" in user_text:
        words = user_text.split()
        for word in words:
            if word.startswith("/"):
                prompt_name = word.replace("/", "").replace("-", " ").strip()
                detected_prompts.append(prompt_name)

    try:
        # If any resources were loaded explicitly, retrieve context first
        injected_context = ""
        if detected_resources:
            print(f"[MCP] Reading live context from resource: {detected_resources[0]}")
            resource_blobs = await mcp_client.get_resources(uris=detected_resources[0])
            if resource_blobs:
                injected_context = resource_blobs[0].as_string()
                user_text += f"\n\n[Mounted Resource Content Context]:\n{injected_context}"

        # If a prompt template was called, construct messages using prompt arguments
        if detected_prompts:
            print(f"[MCP] Retrieving template for prompt: {detected_prompts[0]}")
            # Format arguments safely (e.g. inject extracted context text or defaults)
            args = {"project_details": injected_context or "{}"}
            prompt_messages = await mcp_client.get_prompt(detected_prompts[0], arguments=args)
            messages_payload = prompt_messages
        else:
            # Standard conversational message execution payload
            messages_payload = [{"role": "user", "content": user_text}]

        # Invoke the live compiled LangGraph agent executor
        print(f"[Agent] Executing workflow execution run thread: {thread_id}")
        result = await agent_instance.ainvoke(
            {"messages": messages_payload},
            config=config,
        )

        # Retrieve the final completed assistant payload from the node history list
        final_message = result["messages"][-1].content

        return {
            "sender": "agent",
            "message": final_message,
            "meta": {
                "thread_id": thread_id,
                "prompts_called": detected_prompts,
                "resources_mounted": detected_resources
            }
        }

    except Exception as e:
        print(f"[Agent Error] Failed execution: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to execute real MCP subprocess operation: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)