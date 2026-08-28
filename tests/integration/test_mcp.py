import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_mcp_stdio_tools():
    async def scenario():
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path.cwd() / "src")
        params = StdioServerParameters(command=sys.executable, args=["-m", "finance_insight.mcp_server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"financial_query", "annual_report_search"} <= names
                result = await session.call_tool("financial_query", {"question": "查询凯莱英2024年营业收入"})
                assert not result.is_error

    anyio.run(scenario)

