"""시계열 데이터 CRUD와 분석(요약/통계).

데이터가 1만 건 이상이라 Firestore 전체를 읽으면 무료 한도(일 5만 회 읽기)를 금방 넘는다.
- 요청은 메모리 캐시에서 처리하고, 추가/수정/삭제 시 캐시도 함께 갱신한다.
- 캐시를 채울 때는 통화별 스냅샷 문서(data_snapshots/{통화}) 5개만 읽는다.
  스냅샷이 없을 때만 data 컬렉션 전체를 한 번 읽고 스냅샷을 만든다.
(Render 무료 플랜은 인스턴스 1개라 캐시 불일치 문제가 없다.)
"""
import json
import logging
import statistics as st
import threading
from datetime import date, datetime, timedelta, timezone

from ..currencies import CURRENCIES
from ..db import DATA_COLLECTION, SNAPSHOT_COLLECTION, repo
from ..schemas import DataCreate, DataUpdate

logger = logging.getLogger(__name__)

TREND_WINDOW = 20  # 최근 추세 판단에 쓰는 데이터 개수
TREND_THRESHOLD_PCT = 1.0  # 이 비율 이상 움직이면 증가/감소로 본다


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_cache: dict[str, dict] | None = None
_cache_lock = threading.RLock()


def _load_snapshots() -> dict[str, dict] | None:
    """통화별 스냅샷 5개를 읽는다. 하나라도 없거나 깨져 있으면 None."""
    docs: dict[str, dict] = {}
    for currency in CURRENCIES:
        snap = repo.get(SNAPSHOT_COLLECTION, currency)
        if snap is None:
            return None
        try:
            items = json.loads(snap["payload"])
        except (KeyError, TypeError, ValueError):
            logger.warning("스냅샷 %s 이 손상되어 전체를 다시 읽습니다.", currency)
            return None
        docs.update({i["id"]: i for i in items})
    return docs


def _write_snapshot(currency: str) -> None:
    items = sorted((i for i in _all().values() if i["currency"] == currency), key=lambda i: i["date"])
    repo.set(
        SNAPSHOT_COLLECTION,
        currency,
        {
            # 배열 대신 문자열로 저장한다(배열 필드는 항목마다 색인돼 문서당 색인 한도를 넘는다).
            "payload": json.dumps(items, ensure_ascii=False, separators=(",", ":")),
            "count": len(items),
            "updated_at": _now(),
        },
    )


def _all() -> dict[str, dict]:
    global _cache
    with _cache_lock:
        if _cache is None:
            docs = _load_snapshots()
            if docs is not None:
                _cache = docs
                logger.info("스냅샷에서 데이터 %d건을 불러왔습니다(읽기 %d회).", len(docs), len(CURRENCIES))
            else:
                full = repo.list(DATA_COLLECTION)
                for d in full:
                    d.setdefault("currency", "USD")  # currency 필드 도입 이전 문서 호환
                _cache = {d["id"]: d for d in full}
                logger.info("data 컬렉션 전체 %d건을 읽어 스냅샷을 만듭니다.", len(full))
                # 스냅샷 쓰기가 실패해도 이미 읽은 캐시로 요청은 처리한다(다음 시작 때 다시 시도).
                try:
                    for currency in CURRENCIES:
                        _write_snapshot(currency)
                except Exception:
                    logger.exception("스냅샷 저장에 실패했습니다. 다음 서버 시작 때 전체를 다시 읽습니다.")
        return _cache


def reset_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def add_many_data(rows: list[dict]) -> int:
    """여러 건을 data 컬렉션에 추가하고 캐시와 해당 통화 스냅샷을 갱신한다(스크립트용)."""
    if not rows:
        return 0
    with _cache_lock:
        cache = _all()
        for saved in repo.add_many(DATA_COLLECTION, rows):
            cache[saved["id"]] = saved
        for currency in {r["currency"] for r in rows}:
            _write_snapshot(currency)
    return len(rows)


def rebuild_snapshots(docs: list[dict] | None = None) -> None:
    """스냅샷을 새로 만든다. docs를 주면 그 목록으로, 없으면 data 컬렉션 전체를 다시 읽어서 만든다."""
    global _cache
    with _cache_lock:
        if docs is None:
            docs = repo.list(DATA_COLLECTION)
        _cache = {d["id"]: {**d, "currency": d.get("currency", "USD")} for d in docs}
        for currency in CURRENCIES:
            _write_snapshot(currency)


def list_data(currency: str | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
    items = list(_all().values())
    if currency:
        items = [i for i in items if i["currency"] == currency]
    if start:
        items = [i for i in items if i["date"] >= start]
    if end:
        items = [i for i in items if i["date"] <= end]
    return sorted(items, key=lambda i: (i["date"], i["currency"]))


def create_data(payload: DataCreate) -> dict:
    now = _now()
    doc = {"date": payload.date.isoformat(), "currency": payload.currency, "value": payload.value,
           "memo": payload.memo,
           "created_at": now, "updated_at": now}
    with _cache_lock:
        cache = _all()
        saved = repo.add(DATA_COLLECTION, doc)
        cache[saved["id"]] = saved
        _write_snapshot(saved["currency"])
    return saved


def update_data(doc_id: str, payload: DataUpdate) -> dict | None:
    changes = payload.model_dump(exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    changes["updated_at"] = _now()
    with _cache_lock:
        cache = _all()
        updated = repo.update(DATA_COLLECTION, doc_id, changes)
        if updated is not None:
            updated.setdefault("currency", "USD")
            before = cache.get(doc_id)
            cache[doc_id] = updated
            # 통화가 바뀌면 원래 통화의 스냅샷도 고친다
            for currency in {updated["currency"], before["currency"] if before else updated["currency"]}:
                _write_snapshot(currency)
    return updated


def delete_data(doc_id: str) -> bool:
    with _cache_lock:
        cache = _all()
        deleted = repo.delete(DATA_COLLECTION, doc_id)
        if deleted:
            removed = cache.pop(doc_id, None)
            if removed:
                _write_snapshot(removed["currency"])
    return deleted


def _trend(values: list[float]) -> tuple[str, str]:
    """최근 N개에 선형회귀 기울기를 구해, 구간 동안의 예상 변화율로 추세를 판단한다."""
    window = values[-TREND_WINDOW:]
    n = len(window)
    if n < 3:
        return "데이터 부족", "추세 판단에는 최소 3개의 데이터가 필요합니다."
    xs = range(n)
    x_mean = (n - 1) / 2
    y_mean = sum(window) / n
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, window)) / sum(
        (x - x_mean) ** 2 for x in xs
    )
    change_pct = slope * (n - 1) / y_mean * 100
    if change_pct >= TREND_THRESHOLD_PCT:
        label = "증가"
    elif change_pct <= -TREND_THRESHOLD_PCT:
        label = "감소"
    else:
        label = "유지"
    return label, f"최근 {n}개 데이터의 회귀 기울기 기준 약 {change_pct:+.2f}% 변화"


def _change_since(items: list[dict], days: int) -> float | None:
    """마지막 날짜 기준 N일 전(또는 그 직후 첫 데이터) 대비 변화율(%)."""
    cutoff = (date.fromisoformat(items[-1]["date"]) - timedelta(days=days)).isoformat()
    if items[0]["date"] > cutoff:
        return None
    base = next(i for i in items if i["date"] >= cutoff)["value"]
    return round((items[-1]["value"] - base) / base * 100, 2)


def _currency_info(currency: str) -> dict:
    meta = CURRENCIES[currency]
    return {"currency": currency, "currency_name": meta["name"], "unit": meta["unit"]}


def get_summary(currency: str = "USD", start: str | None = None, end: str | None = None) -> dict:
    items = list_data(currency, start, end)
    if not items:
        return {**_currency_info(currency), "count": 0, "trend": "데이터 부족",
                "trend_detail": "저장된 데이터가 없습니다."}
    values = [i["value"] for i in items]
    max_item = max(items, key=lambda i: i["value"])
    min_item = min(items, key=lambda i: i["value"])
    trend, detail = _trend(values)
    return {
        **_currency_info(currency),
        "count": len(items),
        "period_start": items[0]["date"],
        "period_end": items[-1]["date"],
        "mean": round(st.fmean(values), 2),
        "max": max_item["value"],
        "max_date": max_item["date"],
        "min": min_item["value"],
        "min_date": min_item["date"],
        "first_value": values[0],
        "latest_value": values[-1],
        "change_pct": round((values[-1] - values[0]) / values[0] * 100, 2),
        "change_1y_pct": _change_since(items, days=365),
        "trend": trend,
        "trend_detail": detail,
    }


def get_all_summaries() -> list[dict]:
    """모든 통화의 요약(캐시에서 계산)."""
    return [get_summary(c) for c in CURRENCIES]


def get_statistics(currency: str = "USD", start: str | None = None, end: str | None = None) -> dict:
    items = list_data(currency, start, end)
    values = [i["value"] for i in items]
    result: dict = {"currency": currency, "count": len(values)}
    if len(values) < 2:
        return result

    daily = [(b - a) / a * 100 for a, b in zip(values, values[1:])]
    peak, mdd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        mdd = min(mdd, (v - peak) / peak * 100)

    def group(key_len: int) -> list[dict]:
        groups: dict[str, list[float]] = {}
        for i in items:
            groups.setdefault(i["date"][:key_len], []).append(i["value"])
        return [
            {"period": k, "mean": round(st.fmean(v), 2), "max": max(v), "min": min(v), "count": len(v)}
            for k, v in sorted(groups.items())
        ]

    result.update(
        std=round(st.stdev(values), 2),
        median=round(st.median(values), 2),
        daily_volatility_pct=round(st.stdev(daily), 3) if len(daily) > 1 else None,
        max_drawdown_pct=round(mdd, 2),
        ma7=round(st.fmean(values[-7:]), 2),
        ma30=round(st.fmean(values[-30:]), 2),
        yearly=group(4),
        monthly=group(7),
    )
    return result


def summary_to_text(s: dict) -> str:
    """요약 dict를 시스템 프롬프트에 넣을 문장으로 바꾼다."""
    head = f"[{s['currency']} {s['currency_name']} · {s['unit']}당 원화]"
    if s["count"] == 0:
        return f"{head}\n- 저장된 데이터가 없습니다."
    lines = [
        head,
        f"- 기간: {s['period_start']} ~ {s['period_end']} (총 {s['count']}개)",
        f"- 평균: {s['mean']}원",
        f"- 최고: {s['max']}원 ({s['max_date']}), 최저: {s['min']}원 ({s['min_date']})",
        f"- 시작값 {s['first_value']}원 → 최신값 {s['latest_value']}원 (기간 변화율 {s['change_pct']:+}%)",
    ]
    if s.get("change_1y_pct") is not None:
        lines.append(f"- 최근 1년 변화율: {s['change_1y_pct']:+}%")
    lines.append(f"- 최근 추세: {s['trend']} ({s['trend_detail']})")
    return "\n".join(lines)
