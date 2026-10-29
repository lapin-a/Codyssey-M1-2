"""최신 환율을 받아 빠진 (date, currency)만 추가한다.

출처: Frankfurter API (ECB 기준). 엔화는 100엔당 원화로 저장한다.

사용법 (backend 폴더에서):
    python -m scripts.update_rates              # data/fx_krw.csv 갱신 (기본)
    python -m scripts.update_rates --firestore  # Firestore data 컬렉션에 빠진 날짜만 추가
"""
import csv
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "fx_krw.csv"
MULTIPLIER = {"USD": 1, "EUR": 1, "JPY": 100, "CNY": 1, "GBP": 1}
API = "https://api.frankfurter.app/{start}..{end}?from={currency}&to=KRW"


def memo_for(currency: str) -> str:
    return f"ECB 기준 {currency}/KRW" + (" (100엔당)" if currency == "JPY" else "")


def fetch(currency: str, start: str, end: str) -> list[dict]:
    """start~end 기간의 환율. Python 기본 User-Agent는 403이 나서 직접 지정한다."""
    url = API.format(start=start, end=end, currency=currency)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fx-ai-chat updater)"})
    with urllib.request.urlopen(req, timeout=30) as res:
        rates = json.load(res).get("rates", {})
    return [
        {"date": d, "currency": currency, "value": round(v["KRW"] * MULTIPLIER[currency], 2),
         "memo": memo_for(currency)}
        for d, v in sorted(rates.items())
        if start <= d <= end  # 시작일이 휴일이면 직전 영업일이 섞여 올 수 있다
    ]


def missing_rows(existing: set[tuple[str, str]], last_dates: dict[str, str]) -> list[dict]:
    today = date.today().isoformat()
    rows = []
    for currency in MULTIPLIER:
        last = last_dates.get(currency, "2016-10-09")
        start = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
        if start > today:
            continue
        for row in fetch(currency, start, today):
            if (row["date"], row["currency"]) not in existing:
                rows.append(row)
    return rows


def update_csv() -> None:
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    existing = {(r["date"], r["currency"]) for r in rows}
    last_dates: dict[str, str] = {}
    for r in rows:
        last_dates[r["currency"]] = max(last_dates.get(r["currency"], ""), r["date"])

    new = missing_rows(existing, last_dates)
    if not new:
        print("추가할 데이터가 없습니다. 이미 최신입니다.")
        return
    rows += [{**r, "value": str(r["value"])} for r in new]
    order = list(MULTIPLIER)
    rows.sort(key=lambda r: (order.index(r["currency"]), r["date"]))
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "currency", "value", "memo"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV에 {len(new)}개를 추가했습니다. (총 {len(rows)}개)")


def update_firestore() -> None:
    from app.db import DATA_COLLECTION, repo

    if repo.backend != "firestore":
        sys.exit("Firebase 자격 증명이 없습니다. .env 의 FIREBASE_SERVICE_ACCOUNT_* 를 설정하세요.")
    docs = repo.list(DATA_COLLECTION)
    existing = {(d["date"], d.get("currency", "USD")) for d in docs}
    last_dates: dict[str, str] = {}
    for d, c in existing:
        last_dates[c] = max(last_dates.get(c, ""), d)

    new = missing_rows(existing, last_dates)
    if not new:
        print("추가할 데이터가 없습니다. 이미 최신입니다.")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo.add_many(DATA_COLLECTION, [{**r, "created_at": now, "updated_at": now} for r in new])
    print(f"Firestore에 {len(new)}개를 추가했습니다. (서버를 재시작해야 캐시에 반영됩니다)")


if __name__ == "__main__":
    update_firestore() if "--firestore" in sys.argv else update_csv()
