"""MCP 서버 동작 확인용 클라이언트.

server.py를 stdio로 띄워 도구 목록을 받고, 몇 개 도구를 실제로 호출해 결과를 출력한다.
실행 (저장소 루트에서, 백엔드가 켜져 있어야 함):
    mcp_server/.venv/Scripts/python mcp_server/test_client.py   # Windows
    mcp_server/.venv/bin/python mcp_server/test_client.py       # macOS/Linux
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent / "server.py"


def show(result, limit: int = 600) -> None:
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    status = "ERROR" if result.isError else "OK"
    print(f"  [{status}] {text[:limit]}{' …' if len(text) > limit else ''}\n")


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env={**os.environ, "API_BASE_URL": os.getenv("API_BASE_URL", "http://localhost:8000"),
             "PYTHONIOENCODING": "utf-8"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"서버: {info.serverInfo.name} {info.serverInfo.version}\n")

            tools = await session.list_tools()
            print(f"도구 {len(tools.tools)}개:")
            for t in tools.tools:
                args = ", ".join(t.inputSchema.get("properties", {}))
                print(f"  - {t.name}({args})")
            print()

            calls = [
                ("get_all_summaries", {}),
                ("get_summary", {"currency": "JPY"}),
                ("get_statistics", {"currency": "EUR", "start_date": "2020-01-01", "end_date": "2020-12-31"}),
                ("list_data", {"currency": "USD", "start_date": "2026-10-20", "limit": 5}),
                ("list_conversations", {}),
                ("get_summary", {"currency": "KRW"}),  # 검증 오류 확인
                ("get_conversation", {"conversation_id": "../data/summary"}),  # 경로 조작 방지 확인
            ]
            for name, args in calls:
                print(f"> {name}({json.dumps(args, ensure_ascii=False)})")
                show(await session.call_tool(name, args))


if __name__ == "__main__":
    asyncio.run(main())
