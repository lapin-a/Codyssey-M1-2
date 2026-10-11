"""Pydantic 모델: 요청 본문 검증과 응답 형태를 정의한다."""
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------- 데이터 ----------
class DataCreate(BaseModel):
    date: Date = Field(..., description="YYYY-MM-DD 형식 날짜", examples=["2026-10-09"])
    value: float = Field(..., gt=0, lt=1_000_000, description="원/달러 환율 값", examples=[1341.49])
    memo: str = Field("", max_length=200, description="메모(최대 200자)")

    @field_validator("date")
    @classmethod
    def not_future(cls, v: Date) -> Date:
        if v > Date.today():
            raise ValueError("미래 날짜는 입력할 수 없습니다.")
        return v

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataUpdate(BaseModel):
    """부분 수정: 보낸 필드만 바뀐다."""

    date: Date | None = None
    value: float | None = Field(None, gt=0, lt=1_000_000)
    memo: str | None = Field(None, max_length=200)

    @field_validator("date")
    @classmethod
    def not_future(cls, v: Date | None) -> Date | None:
        if v is not None and v > Date.today():
            raise ValueError("미래 날짜는 입력할 수 없습니다.")
        return v


class DataItem(BaseModel):
    id: str
    date: str
    value: float
    memo: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class DataList(BaseModel):
    total: int
    items: list[DataItem]


class Summary(BaseModel):
    count: int
    period_start: str | None = None
    period_end: str | None = None
    mean: float | None = None
    max: float | None = None
    max_date: str | None = None
    min: float | None = None
    min_date: str | None = None
    first_value: float | None = None
    latest_value: float | None = None
    change_pct: float | None = Field(None, description="기간 전체 변화율(%)")
    trend: Literal["증가", "감소", "유지", "데이터 부족"]
    trend_detail: str = ""


class Statistics(BaseModel):
    count: int
    std: float | None = None
    median: float | None = None
    daily_volatility_pct: float | None = Field(None, description="일간 변화율의 표준편차(%)")
    max_drawdown_pct: float | None = Field(None, description="최고점 대비 최대 하락률(%)")
    ma7: float | None = Field(None, description="최근 7개 이동평균")
    ma30: float | None = Field(None, description="최근 30개 이동평균")
    monthly: list[dict] = Field(default_factory=list, description="월별 평균/최대/최소")


# ---------- 대화 ----------
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    created_at: str | None = None


class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    messages: list[Message] = Field(..., min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    """목록 조회용: messages는 포함하지 않는다(용량 절약). 전체는 GET /api/conversations/{id}."""

    id: str
    title: str
    message_count: int
    created_at: str | None = None
    updated_at: str | None = None


class Conversation(ConversationSummary):
    messages: list[Message]


# ---------- 채팅 ----------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="사용자 질문")
    conversation_id: str | None = Field(None, description="이어서 대화할 대화 ID(없으면 새 대화)")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 메시지는 보낼 수 없습니다.")
        return v.strip()


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    reason: str = ""


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    summary: Summary
    tool_calls: list[ToolCallLog] = Field(default_factory=list)
