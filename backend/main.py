"""FastAPI 진입점: 앱 생성, CORS, 라우터 등록."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from app.db import repo
from app.routers import chat, conversations, data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="환율 데이터 AI 챗봇 API",
    description="원/달러 환율 시계열 데이터 CRUD, 요약, 대화 기록, GPT 채팅(컨텍스트 주입)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


@app.get("/", tags=["health"], summary="서버 상태")
def root():
    return {"status": "ok", "storage": repo.backend, "docs": "/docs"}


@app.get("/health", tags=["health"], summary="헬스 체크(콜드스타트 깨우기용)")
def health():
    return {"status": "ok"}
