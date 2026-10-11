"""시계열 데이터 CRUD와 분석(요약/통계)."""
import statistics as st
from datetime import datetime, timezone

from ..db import DATA_COLLECTION, repo
from ..schemas import DataCreate, DataUpdate

TREND_WINDOW = 20  # 최근 추세 판단에 쓰는 데이터 개수
TREND_THRESHOLD_PCT = 1.0  # 이 비율 이상 움직이면 증가/감소로 본다


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_data(start: str | None = None, end: str | None = None) -> list[dict]:
    items = repo.list(DATA_COLLECTION)
    if start:
        items = [i for i in items if i["date"] >= start]
    if end:
        items = [i for i in items if i["date"] <= end]
    return sorted(items, key=lambda i: i["date"])


def create_data(payload: DataCreate) -> dict:
    now = _now()
    doc = {"date": payload.date.isoformat(), "value": payload.value, "memo": payload.memo,
           "created_at": now, "updated_at": now}
    return repo.add(DATA_COLLECTION, doc)


def update_data(doc_id: str, payload: DataUpdate) -> dict | None:
    changes = payload.model_dump(exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    changes["updated_at"] = _now()
    return repo.update(DATA_COLLECTION, doc_id, changes)


def delete_data(doc_id: str) -> bool:
    return repo.delete(DATA_COLLECTION, doc_id)


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


def get_summary(start: str | None = None, end: str | None = None) -> dict:
    items = list_data(start, end)
    if not items:
        return {"count": 0, "trend": "데이터 부족", "trend_detail": "저장된 데이터가 없습니다."}
    values = [i["value"] for i in items]
    max_item = max(items, key=lambda i: i["value"])
    min_item = min(items, key=lambda i: i["value"])
    trend, detail = _trend(values)
    return {
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
        "trend": trend,
        "trend_detail": detail,
    }


def get_statistics(start: str | None = None, end: str | None = None) -> dict:
    items = list_data(start, end)
    values = [i["value"] for i in items]
    result: dict = {"count": len(values)}
    if len(values) < 2:
        return result

    daily = [(b - a) / a * 100 for a, b in zip(values, values[1:])]
    peak, mdd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        mdd = min(mdd, (v - peak) / peak * 100)

    months: dict[str, list[float]] = {}
    for i in items:
        months.setdefault(i["date"][:7], []).append(i["value"])

    result.update(
        std=round(st.stdev(values), 2),
        median=round(st.median(values), 2),
        daily_volatility_pct=round(st.stdev(daily), 3) if len(daily) > 1 else None,
        max_drawdown_pct=round(mdd, 2),
        ma7=round(st.fmean(values[-7:]), 2),
        ma30=round(st.fmean(values[-30:]), 2),
        monthly=[
            {"month": m, "mean": round(st.fmean(v), 2), "max": max(v), "min": min(v), "count": len(v)}
            for m, v in sorted(months.items())
        ],
    )
    return result


def summary_to_text(s: dict) -> str:
    """요약 dict를 시스템 프롬프트에 넣을 문장으로 바꾼다."""
    if s["count"] == 0:
        return "현재 저장된 데이터가 없습니다."
    return (
        f"- 데이터: 원/달러(USD/KRW) 일별 환율\n"
        f"- 기간: {s['period_start']} ~ {s['period_end']} (총 {s['count']}개)\n"
        f"- 평균: {s['mean']}원\n"
        f"- 최고: {s['max']}원 ({s['max_date']}), 최저: {s['min']}원 ({s['min_date']})\n"
        f"- 시작값 {s['first_value']}원 → 최신값 {s['latest_value']}원 (기간 변화율 {s['change_pct']:+}%)\n"
        f"- 최근 추세: {s['trend']} ({s['trend_detail']})"
    )
