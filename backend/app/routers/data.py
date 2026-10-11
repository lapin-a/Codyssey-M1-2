import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from ..currencies import Currency
from ..schemas import DataCreate, DataItem, DataList, DataUpdate, Statistics, Summary
from ..services import data_service

router = APIRouter(prefix="/api/data", tags=["data"])

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
StartQ = Query(None, pattern=DATE_PATTERN, description="시작일 YYYY-MM-DD")
EndQ = Query(None, pattern=DATE_PATTERN, description="종료일 YYYY-MM-DD")
CurrencyQ = Query("USD", description="통화 코드")
OptCurrencyQ = Query(None, description="통화 코드(없으면 전체)")


# 고정 경로(/summary 등)는 /{doc_id}보다 먼저 선언한다.
@router.get("/summary", response_model=Summary, summary="통화별 데이터 요약(프롬프트 주입용)")
def get_summary(currency: Currency = CurrencyQ, start: str | None = StartQ, end: str | None = EndQ):
    return data_service.get_summary(currency, start, end)


@router.get("/summary/all", response_model=list[Summary], summary="전체 통화 요약")
def get_all_summaries():
    return data_service.get_all_summaries()


@router.get("/statistics", response_model=Statistics, summary="통화별 상세 통계(보너스)")
def get_statistics(currency: Currency = CurrencyQ, start: str | None = StartQ, end: str | None = EndQ):
    return data_service.get_statistics(currency, start, end)


@router.get("/export", summary="데이터 내보내기(CSV/JSON)")
def export_data(format: Literal["csv", "json"] = "csv", currency: Currency | None = OptCurrencyQ):
    items = [{"date": i["date"], "currency": i["currency"], "value": i["value"], "memo": i.get("memo", "")}
             for i in data_service.list_data(currency)]
    if format == "json":
        body = json.dumps(items, ensure_ascii=False, indent=2)
        media = "application/json"
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["date", "currency", "value", "memo"])
        writer.writeheader()
        writer.writerows(items)
        body = "﻿" + buf.getvalue()  # 엑셀 한글 깨짐 방지용 BOM
        media = "text/csv; charset=utf-8"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{(currency or "all").lower()}_krw.{format}"'},
    )


@router.get("", response_model=DataList, summary="데이터 목록 조회(날짜 오름차순)")
def list_data(currency: Currency | None = OptCurrencyQ, start: str | None = StartQ, end: str | None = EndQ):
    items = data_service.list_data(currency, start, end)
    return {"total": len(items), "items": items}


@router.post("", response_model=DataItem, status_code=status.HTTP_201_CREATED, summary="새 데이터 추가")
def create_data(payload: DataCreate):
    return data_service.create_data(payload)


@router.put("/{doc_id}", response_model=DataItem, summary="데이터 수정")
def update_data(doc_id: str, payload: DataUpdate):
    if not payload.model_dump(exclude_none=True):
        raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")
    updated = data_service.update_data(doc_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    return updated


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="데이터 삭제")
def delete_data(doc_id: str):
    if not data_service.delete_data(doc_id):
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
