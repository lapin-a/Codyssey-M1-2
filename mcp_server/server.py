"""환율 AI 챗봇의 기능을 MCP 도구로 노출하는 서버.

웹 채팅의 GPT가 Function Calling으로 쓰는 것과 같은 기능을, Claude 같은 외부 MCP 클라이언트도
부를 수 있게 한다. 각 도구는 FastAPI 백엔드를 HTTP로 호출하므로 웹 서비스와 같은 데이터를 본다.

실행: python mcp_server/server.py   (stdio 전송, 클라이언트가 프로세스를 띄워 연결)
환경 변수: API_BASE_URL (기본 http://localhost:8000)
"""
import os
from urllib.parse import quote
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 70  # Render 무료 플랜 콜드스타트(최대 1분)를 고려
MAX_MONTHLY_ROWS = 24  # 웹 채팅 도구와 같은 기준으로 월별 통계를 자른다

Currency = Literal["USD", "EUR", "JPY", "CNY", "GBP"]

mcp = FastMCP(
    "fx-ai-chat",
    instructions=(
        "원화(KRW) 기준 환율 데이터(USD 달러, EUR 유로, JPY 엔(100엔당), CNY 위안, GBP 파운드, 2016-10 이후 일별)와 "
        "저장된 AI 대화 기록을 조회한다. 전체 흐름은 get_all_summaries로 먼저 보고, "
        "특정 기간·지표가 필요하면 get_statistics나 list_data를 쓴다."
    ),
)


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """백엔드 GET 호출. 실패하면 사람이 읽을 수 있는 메시지로 바꿔 ToolError를 낸다."""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            res = await client.get(path, params=params)
    except httpx.TimeoutException:
        raise ToolError(f"백엔드 응답 시간 초과({TIMEOUT}초): {API_BASE_URL}. 서버가 잠들어 있으면 잠시 후 다시 시도하세요.")
    except httpx.HTTPError as e:
        raise ToolError(f"백엔드에 연결할 수 없습니다: {API_BASE_URL} ({e.__class__.__name__}). API_BASE_URL과 서버 실행 여부를 확인하세요.")

    if res.status_code >= 400:
        try:
            detail = res.json().get("detail")
        except ValueError:
            detail = res.text[:200]
        if isinstance(detail, list):  # FastAPI 422 검증 오류
            detail = "; ".join(f"{'.'.join(map(str, d.get('loc', [])))}: {d.get('msg')}" for d in detail)
        raise ToolError(f"백엔드 오류 {res.status_code}: {detail}")
    return res.json()


@mcp.tool()
async def get_summary(currency: Currency = "USD") -> dict:
    """한 통화의 전체 기간 요약: 기간, 데이터 개수, 평균, 최고/최저(날짜), 시작값/최신값, 기간 변화율,
    최근 1년 변화율, 최근 추세(증가/감소/유지). 값은 원화이며 JPY는 100엔당 금액이다."""
    return await _get("/api/data/summary", {"currency": currency})


@mcp.tool()
async def get_all_summaries() -> list[dict]:
    """5개 통화(USD, EUR, JPY, CNY, GBP)의 요약을 한 번에 조회한다. 통화끼리 비교하거나
    "가장 많이 오른/떨어진 통화"를 물을 때 먼저 사용한다."""
    return await _get("/api/data/summary/all")


@mcp.tool()
async def get_statistics(
    currency: Currency = "USD",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """한 통화의 상세 통계: 표준편차, 중앙값, 일간 변동성(일간 변화율의 표준편차, %), 최대 낙폭(MDD, %),
    7/30일 이동평균, 연도별·월별 평균/최고/최저. 날짜는 YYYY-MM-DD이며 생략하면 전체 기간이다.
    월별 통계는 최근 24개월만 돌려주므로, 그 이전 월이 필요하면 기간을 좁혀서 호출한다."""
    stats = await _get(
        "/api/data/statistics", {"currency": currency, "start": start_date, "end": end_date}
    )
    if len(stats.get("monthly", [])) > MAX_MONTHLY_ROWS:
        stats["monthly"] = stats["monthly"][-MAX_MONTHLY_ROWS:]
        stats["note"] = f"월별 통계는 최근 {MAX_MONTHLY_ROWS}개월만 포함. 이전 월은 기간을 좁혀 다시 조회."
    return stats


@mcp.tool()
async def list_data(
    currency: Currency = "USD",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 30,
) -> list[dict]:
    """한 통화의 일별 원본 데이터(date, value, memo)를 날짜 오름차순으로 조회한다.
    지정한 기간에서 가장 최근 limit개(1~60)만 돌려준다. 특정 날짜의 값을 확인할 때 사용한다.
    주말·공휴일에는 데이터가 없다."""
    limit = max(1, min(limit, 60))
    res = await _get("/api/data", {"currency": currency, "start": start_date, "end": end_date})
    return [
        {"date": i["date"], "value": i["value"], "memo": i.get("memo", "")}
        for i in res["items"][-limit:]
    ]


@mcp.tool()
async def list_conversations() -> list[dict]:
    """웹 채팅에서 저장된 AI 대화 목록(id, 제목, 메시지 수, 생성/수정 시각)을 최근 수정순으로 조회한다.
    메시지 본문은 포함하지 않으므로, 내용은 get_conversation으로 본다."""
    return await _get("/api/conversations")


@mcp.tool()
async def get_conversation(conversation_id: str) -> dict:
    """저장된 대화 하나의 전체 메시지(role, content, created_at)를 조회한다.
    conversation_id는 list_conversations 결과의 id 값이다."""
    # id에 "/"나 ".." 가 섞여 다른 경로를 부르지 않도록 인코딩한다
    return await _get(f"/api/conversations/{quote(conversation_id, safe='')}")


if __name__ == "__main__":
    mcp.run()  # 기본 stdio 전송
