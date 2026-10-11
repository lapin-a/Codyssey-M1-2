from fastapi import APIRouter, HTTPException, status

from ..schemas import Conversation, ConversationCreate, ConversationSummary
from ..services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=Conversation, status_code=status.HTTP_201_CREATED, summary="대화 저장")
def create_conversation(payload: ConversationCreate):
    messages = [m.model_dump() for m in payload.messages]
    return conversation_service.create_conversation(payload.title.strip(), messages)


@router.get(
    "",
    response_model=list[ConversationSummary],
    summary="대화 목록 조회(messages 미포함, 최근 수정순)",
)
def list_conversations():
    return conversation_service.list_conversations()


@router.get("/{conv_id}", response_model=Conversation, summary="특정 대화 전체 메시지 조회")
def get_conversation(conv_id: str):
    conv = conversation_service.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return conv


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT, summary="대화 삭제")
def delete_conversation(conv_id: str):
    if not conversation_service.delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
