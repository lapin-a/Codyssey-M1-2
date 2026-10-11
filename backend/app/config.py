"""환경 변수 로드. 키 값은 코드에 두지 않고 .env 또는 배포 환경 변수에서만 읽는다."""
import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None  # 프록시/호환 서버 사용 시
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
# gpt-5 계열은 추론 토큰도 이 한도에 포함되므로 너무 작게 잡으면 빈 답변이 나온다.
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",")
    if o.strip()
]
