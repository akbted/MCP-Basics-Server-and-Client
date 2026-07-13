from config import settings, get_llmclient, ROOT, get_ollamaclient
from  mcp_client import MCPClient

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.utils.uuid import uuid7

from typing import Optional, Any, Dict
import json


# llm = get_llmclient()
llm = get_ollamaclient()
mcp_client: Optional[MCPClient] = None
agent_instance: Optional[Any] = None

# Lifespan Managment
@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_client, agent_instance

    mcp_client = MCPClient("python", [f"{ROOT}/src/mcp_server.py"])
    await mcp_client.connect()

    mcp_tools = await mcp_client.get_tools()

    agent_instance = create_agent(
        model=llm,
        system_prompt="You are a helpful assistant. Be concise and accurate.",
        checkpointer=InMemorySaver(),
        tools=mcp_tools
    )

    print("[MCP Engine] All systems successfully initialized and ready!")
    yield
    print("[MCP Engine] Shutting down connected subprocess channels...")


# FastAPI
app = FastAPI(
    title="Real MCP Agent Host Server",
    description="Live FastAPI server executing standard LangGraph agent models over physical subprocess contexts",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints
@app.get("/")
async def get_servers():
    """ROOT"""
    return [
        {
            "message" : "Backend for OpenProject Agentic Framework (ArcaAi)",
            "developed_by" : "Anantha Krishna",
            "status": 200
        }
    ]


@app.get("/v1/api/servers")
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

@app.get("/v1/api/prompts")
async def get_prompts():
    """
    Dynamically lists all prompt templates registered on the target subserver.
    """
    if not mcp_client:
        return []
    try:
        raw_prompts = await mcp_client.list_prompts()
        return [
            {"name": p.name, "desc": p.description or "Active prompt template", "content": ""}
            for p in raw_prompts
        ]
    except Exception as e:
        print(f"Error: {e}")
        return [
            {"status": "prompts not implemented"}
        ]


@app.get("/v1/api/resources")
async def get_resources():
    """
    Dynamically lists resources from the live sub-server.
    """
    if not mcp_client:
        return []
    try:
        static_resources = await mcp_client.list_resources()
        templates = await mcp_client.list_resource_templates()
        return [
            {"name": r.name, "desc": r.description or "Local data file context",
             "content": str(r.uri), "template": False}
            for r in static_resources
        ] + [
            {"name": t.name, "desc": t.description or "Parameterized resource",
             "content": t.uriTemplate, "template": True}
            for t in templates
        ]
    except Exception as e:
        return [
            {"status": "prompts not implemented"}
        ]
    
@app.post("/v1/api/chat")
async def process_agent_chat(payload: Dict):
    """
    Parses active workspace entries, executes resource injections from standard
    file paths, runs live tool execution requests, and returns agent final output.
    """
    if not agent_instance or not mcp_client:
        raise HTTPException(status_code=500, detail="MCP Backend engine is not initialized.")
    
    user_text = payload.get("message", "")
    messages_payload = []

    thread_id = str(uuid7())
    config = {"configurable": {"thread_id": thread_id}}

    detected_prompts = []
    detected_resources = []

    if "@" in user_text:
        words = user_text.split()
        for word in words:
            if word.startswith("@"):
                res_target = word.replace("@", "").strip()
                if res_target.startswith("openproject://projects/active"):
                    res_target = f"openproject://projects/{res_target}/work-packages"
                    detected_resources.append(res_target)
                elif res_target.startswith("openproject://projects/"):
                    res_target = f"openproject://projects/{res_target}/work-packages"
                    detected_resources.append(res_target)
                elif res_target.startswith("openproject://work-packages/"):
                    res_target = f"openproject://work-packages/{res_target}"
                    detected_resources.append(res_target)
                elif res_target.startswith("openproject://outputs"):
                    detected_resources.append(res_target)

    if "/" in user_text:
        words = user_text.split()
        for word in words:
            if word.startswith("/"):
                prompt_name = word.replace("/", "").replace("-", " ").strip()
                detected_prompts.append(prompt_name)

    try:
        injected_context = ""
        if detected_resources:
            resource = await mcp_client.get_resources(uris=detected_resources[0])
            if resource:
                injected_context = resource[0].as_string()
                user_text += f"\n\n[Mounted Resource Content Context]:\n{injected_context}"

        if detected_prompts:
            args = {"project_details": injected_context or "{}"}
            prompt_messages = await mcp_client.get_prompt(detected_prompts[0], arguments=args)
            messages_payload = prompt_messages
        
        else:
            messages_payload = [{"role": "user", "content": user_text}]

            # result = await agent_instance.ainvoke(
            # {"messages": messages_payload},
            # config=config,
            # )

            # final_message = result["messages"][-1].content

        #     return {
        #     "sender": "agent",
        #     "message": final_message,
        #     "meta": {
        #         "thread_id": thread_id,
        #         "prompts_called": detected_prompts,
        #         "resources_mounted": detected_resources
        #     }
        # }


        async def event_generator():
            try:
                # astream_events yields structured events (v2 is recommended for LangChain/LangGraph)
                async for event in agent_instance.astream_events(
                    {"messages": messages_payload},
                    config=config,
                    version="v2"
                ):
                    event_kind = event["event"]

                    # 1. Stream raw model output tokens as they are generated
                    if event_kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if hasattr(chunk, "content") and chunk.content:
                            data = json.dumps({"type": "token", "content": chunk.content})
                            yield f"data: {data}\n\n"

                    # 2. (Optional) Stream when the agent starts executing an MCP tool
                    elif event_kind == "on_tool_start":
                        tool_name = event.get("name")
                        data = json.dumps({"type": "tool_start", "tool": tool_name})
                        yield f"data: {data}\n\n"

                    # 3. (Optional) Stream when the tool finishes running
                    elif event_kind == "on_tool_end":
                        data = json.dumps({"type": "tool_end"})
                        yield f"data: {data}\n\n"

                # Signal end of stream
                yield "data: [DONE]\n\n"

            except Exception as e:
                error_data = json.dumps({"type": "error", "message": str(e)})
                yield f"data: {error_data}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Prevents Nginx/proxies from buffering streams
            }
        )

    except Exception as e:
        print(f"[Agent Error] Failed execution: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to execute real MCP subprocess operation: {str(e)}"
        )




if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
                

                    




