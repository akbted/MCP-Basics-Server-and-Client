from dotenv import load_dotenv
from typing import Optional
import httpx
import os

from mcp.server.mcpserver import MCPServer
import logging

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(name=__name__)

mcp = MCPServer(
    name="OpenProject Management", 
    log_level="INFO"
)


OPENPROJECT_APIROOT = os.getenv("OPENPROJECT_APIROOT")
OPENPROJECT_TOKEN = os.getenv("OPENPROJECT_TOKEN")

class OpenProjectClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=OPENPROJECT_APIROOT,
                auth=httpx.BasicAuth("apikey", OPENPROJECT_TOKEN),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=15.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self):
        await self._client.aclose()


op_server = OpenProjectClient()
