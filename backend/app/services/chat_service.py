"""AI 채팅: 데이터 요약을 시스템 프롬프트에 주입(컨텍스트 주입)하고,
필요하면 GPT가 내부 기능을 도구(Function Calling)로 호출하게 한다."""
import json
import logging
from datetime import datetime, timezone

from openai import OpenAI, OpenAIError

from .. import config
from . import conversation_service, data_service

logger = logging.getLogger(__name__)

MAX_HISTORY = 10  # 이전 대화 중 프롬프트에 넣을 최대 메시지 수
MAX_TOOL_ROUNDS = 3  # 도구 호출 반복 상한(비용/무한루프 방지)

SYSTEM_TEMPLATE = """당신은 원/달러 환율 데이터를 분석해 주는 한국어 어시스턴트입니다.
아래는 데이터베이스에 저장된 데이터의 최신 요약입니다. 답변은 반드시 이 수치에 근거하세요.

[데이터 요약]
{summary}

규칙:
- 요약에 없는 특정 기간·월별 수치나 변동성 같은 세부 정보가 필요하면 제공된 도구를 호출하세요.
- 도구를 호출할 때는 reason 인자에 왜 그 도구가 필요한지 한 문장으로 적으세요.
- 데이터에 없는 내용은 추측하지 말고 모른다고 말하세요. 투자 조언은 하지 마세요.
- 답변은 간결하게, 숫자에는 단위(원, %)를 붙이세요."""

_period_props = {
    "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD (선택)"},
    "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD (선택)"},
    "reason": {"type": "string", "description": "이 도구를 호출하는 이유(한 문장)"},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "지정한 기간의 데이터 요약(개수, 평균, 최고/최저, 변화율, 추세)을 구한다. 특정 기간을 물을 때 사용.",
            "parameters": {"type": "object", "properties": _period_props, "required": ["reason"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "표준편차, 중앙값, 일간 변동성, 최대 낙폭, 이동평균(7/30), 월별 평균 등 상세 통계를 구한다.",
            "parameters": {"type": "object", "properties": _period_props, "required": ["reason"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_data",
            "description": "지정한 기간의 원본 데이터(date, value, memo)를 최대 limit개 조회한다. 특정 날짜 값을 물을 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    **_period_props,
                    "limit": {"type": "integer", "description": "최대 개수(기본 30, 최대 60)"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_conversations",
            "description": "저장된 이전 대화 목록(제목, 메시지 수, 시각)을 조회한다. 사용자가 이전 대화를 물을 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {"reason": _period_props["reason"]},
                "required": ["reason"],
            },
        },
    },
]


class ChatError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_tool(name: str, args: dict):
    start, end = args.get("start_date"), args.get("end_date")
    if name == "get_data_summary":
        return data_service.get_summary(start, end)
    if name == "get_statistics":
        return data_service.get_statistics(start, end)
    if name == "list_data":
        limit = max(1, min(int(args.get("limit") or 30), 60))
        items = data_service.list_data(start, end)[-limit:]
        return [{"date": i["date"], "value": i["value"], "memo": i.get("memo", "")} for i in items]
    if name == "list_conversations":
        return conversation_service.list_conversations()[:20]
    return {"error": f"알 수 없는 도구: {name}"}


def chat(message: str, conversation_id: str | None) -> dict:
    if not config.OPENAI_API_KEY:
        raise ChatError(503, "OPENAI_API_KEY가 설정되지 않았습니다.")

    history: list[dict] = []
    if conversation_id:
        conv = conversation_service.get_conversation(conversation_id)
        if conv is None:
            raise ChatError(404, "대화를 찾을 수 없습니다.")
        history = conv["messages"][-MAX_HISTORY:]

    # 1) 데이터 요약 조회  2) 시스템 프롬프트에 주입
    summary = data_service.get_summary()
    system_prompt = SYSTEM_TEMPLATE.format(summary=data_service.summary_to_text(summary))
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})

    # 3) GPT 호출 (필요 시 도구 호출을 반복)
    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL, timeout=40)
    tool_logs: list[dict] = []
    reply = ""
    try:
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            allow_tools = round_no < MAX_TOOL_ROUNDS
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                max_completion_tokens=config.OPENAI_MAX_TOKENS,
                **({"tools": TOOLS} if allow_tools else {}),
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                reply = msg.content or ""
                break
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(call.function.name, args)
                tool_logs.append(
                    {"name": call.function.name, "arguments": args, "reason": args.get("reason", "")}
                )
                logger.info("tool call %s %s", call.function.name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id,
                     "content": json.dumps(result, ensure_ascii=False)}
                )
    except OpenAIError as e:
        logger.exception("OpenAI 호출 실패")
        raise ChatError(502, f"AI 응답 생성에 실패했습니다: {e.__class__.__name__}") from e

    # 4) 대화 자동 저장
    now = _now()
    new_messages = [
        {"role": "user", "content": message, "created_at": now},
        {"role": "assistant", "content": reply, "created_at": now},
    ]
    if conversation_id:
        conversation_service.append_messages(conversation_id, new_messages)
    else:
        title = message if len(message) <= 30 else message[:30] + "…"
        conversation_id = conversation_service.create_conversation(title, new_messages)["id"]

    return {"conversation_id": conversation_id, "reply": reply, "summary": summary, "tool_calls": tool_logs}
