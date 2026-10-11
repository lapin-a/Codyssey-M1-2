"""지원 통화 목록. 값은 모두 원화(KRW) 기준이며 엔화는 100엔당 금액이다."""
from typing import Literal

Currency = Literal["USD", "EUR", "JPY", "CNY", "GBP"]

CURRENCIES: dict[str, dict[str, str]] = {
    "USD": {"name": "미국 달러", "unit": "1달러"},
    "EUR": {"name": "유로", "unit": "1유로"},
    "JPY": {"name": "일본 엔", "unit": "100엔"},
    "CNY": {"name": "중국 위안", "unit": "1위안"},
    "GBP": {"name": "영국 파운드", "unit": "1파운드"},
}
