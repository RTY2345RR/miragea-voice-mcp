"""List the tools of the voiceover & captions MCP server over stdio (no API key needed).

    uv run --with mcp python examples/list_tools.py
"""

import asyncio
import shutil

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GIT_SOURCE = "git+https://github.com/RTY2345RR/miragea-voice-mcp"


async def main() -> None:
    if shutil.which("miragea-voice-mcp"):
        params = StdioServerParameters(command="miragea-voice-mcp", args=[])
    else:
        params = StdioServerParameters(command="uvx", args=["--from", GIT_SOURCE, "miragea-voice-mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            for tool in tools:
                print(f"{tool.name:<28} {tool.description.split('. ')[0]}")
            print(f"{len(tools)} tools ready")


if __name__ == "__main__":
    asyncio.run(main())
