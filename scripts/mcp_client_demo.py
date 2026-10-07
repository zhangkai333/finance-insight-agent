from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "finance_insight.mcp_server"],
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            query = await session.call_tool(
                "financial_query",
                {"question": "查询凯莱英2024年营业收入"},
            )
            search = await session.call_tool(
                "annual_report_search",
                {
                    "question": "结合年报解释凯莱英2024年营业收入变化原因",
                    "query": "营业收入变化主要原因",
                    "top_k": 3,
                },
            )
    print(json.dumps({
        "tools": [tool.name for tool in tools.tools],
        "financial_query": query.model_dump(mode="json"),
        "annual_report_search": search.model_dump(mode="json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
