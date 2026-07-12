from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.utils.uuid import uuid7
from config import settings, ROOT
from mcp_client import MCPClient

MODEL_NAME = "nvidia/nemotron-3-super-120b-a12b:free"

llm = ChatOpenRouter(
    model=MODEL_NAME,
    api_key=settings.OPENROUTER
)

mcp = MCPClient("python", [f"{ROOT}/src/mcp_server.py"])



async def main():
    client = await mcp.connect()
    
    agent = create_agent(
    model=llm,
    system_prompt="You are a helpful assistant. Be concise and accurate.",
    checkpointer=InMemorySaver(),
    tools=await client.get_tools()
    )


    config = {"configurable": {"thread_id": str(uuid7())}}

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Get me the work packages releated to TrueClaim project - the id is 3"}]},
        config=config,
    )

    # print(result)
    print(result["messages"][-1].content)

    resource_blobs = await mcp.get_resources(uris="file:///outputs/project_details.json")
    project_details_text = resource_blobs[0].as_string()

    prompt_messages = await mcp.get_prompt(
        "Get Updates",
        arguments={"project_details": project_details_text}
    )

    result = await agent.ainvoke(
        {"messages": prompt_messages},
        config=config,
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())