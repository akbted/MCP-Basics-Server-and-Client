import asyncio
from typing import Optional, Any
from langchain_mcp_adapters.client import MultiServerMCPClient
from config import ROOT

class MCPClient:
    def __init__(self, command: str, args: list[str], env: Optional[dict] = None,
    ):
        self._command = command
        self._server_name = "openproject-mcp"
        self._args = args
        self._env = env
        self._session: Optional[MultiServerMCPClient]  = None
    
    async def connect(self):
        client = MultiServerMCPClient(
            connections= {
                self._server_name : {
                    "command" : self._command,
                    "args" : self._args, # [f"{ROOT}/src/mcp_server.py"],
                    "transport" : "stdio",
                    **({"env": self._env} if self._env else {}),
                }
            }
        )
        if self._session is None:
            self._session = client

        return self._session
    
    def session(self) -> MultiServerMCPClient:
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized or cache not populated. Call connect_to_server first."
            )
        return self._session
    
    async def get_tools(self):
        return await self.session().get_tools()
    
    async def get_prompt(self, prompt_name: str, arguments: dict[str, Any] | None = None):
        return await self.session().get_prompt(
            self._server_name, prompt_name, arguments=arguments
        )

    async def get_resources(self,  uris: str | list[str] | None = None):
        return await self.session().get_resources(self._server_name, uris=uris)




async def main_run():
    mcp = MCPClient("python", [f"{ROOT}/src/mcp_server.py"])
    client = await mcp.connect()
    tools = await client.get_tools()
    print(tools)

    prompt_messages = await mcp.get_prompt(
        "Get Updates",
        arguments={"project_details": "{}"}
    )
    print(prompt_messages)

    resources = await mcp.get_resources(uris="file:///outputs")
    for blob in resources:
        print(blob.as_string())



if __name__ == "__main__":
    asyncio.run(main_run())
