from fastapi import APIRouter, HTTPException

from ..schemas import ChatRequest, ChatResponse
from ..services import chat_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="AI 채팅(데이터 요약 주입 + 자동 저장)")
def chat(payload: ChatRequest):
    try:
        return chat_service.chat(payload.message, payload.conversation_id)
    except chat_service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
