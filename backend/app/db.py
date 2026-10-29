"""Firestore 연결과 저장소 추상화.

서비스 계정 정보가 없으면 로컬 개발용 메모리 저장소로 동작한다(서버 재시작 시 초기화).
배포 환경에서는 반드시 Firestore 자격 증명을 설정해야 한다.
"""
from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy
from typing import Any

from . import config

logger = logging.getLogger(__name__)

DATA_COLLECTION = "data"
CONVERSATIONS_COLLECTION = "conversations"
# 통화별 전체 데이터를 JSON 문자열 하나로 담은 문서. 서버 시작 시 1.3만 건 대신 5건만 읽기 위함.
SNAPSHOT_COLLECTION = "data_snapshots"


class FirestoreRepo:
    backend = "firestore"

    def __init__(self, client):
        self.client = client

    def list(self, collection: str) -> list[dict[str, Any]]:
        return [{"id": d.id, **d.to_dict()} for d in self.client.collection(collection).stream()]

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snap = self.client.collection(collection).document(doc_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    def add(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        ref = self.client.collection(collection).document()
        ref.set(data)
        return {"id": ref.id, **data}

    def set(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self.client.collection(collection).document(doc_id).set(data)

    def update(self, collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        ref = self.client.collection(collection).document(doc_id)
        if not ref.get().exists:
            return None
        ref.update(data)
        return self.get(collection, doc_id)

    def delete(self, collection: str, doc_id: str) -> bool:
        ref = self.client.collection(collection).document(doc_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def add_many(self, collection: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Firestore batch는 최대 500건
        saved = []
        for i in range(0, len(items), 400):
            batch = self.client.batch()
            for item in items[i : i + 400]:
                ref = self.client.collection(collection).document()
                batch.set(ref, item)
                saved.append({"id": ref.id, **item})
            batch.commit()
        return saved

    def delete_many(self, collection: str, doc_ids: list[str]) -> int:
        for i in range(0, len(doc_ids), 400):
            batch = self.client.batch()
            for doc_id in doc_ids[i : i + 400]:
                batch.delete(self.client.collection(collection).document(doc_id))
            batch.commit()
        return len(doc_ids)


class MemoryRepo:
    backend = "memory"

    def __init__(self):
        self.store: dict[str, dict[str, dict[str, Any]]] = {}

    def _col(self, collection: str) -> dict[str, dict[str, Any]]:
        return self.store.setdefault(collection, {})

    def list(self, collection: str) -> list[dict[str, Any]]:
        return [{"id": k, **deepcopy(v)} for k, v in self._col(collection).items()]

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._col(collection).get(doc_id)
        return {"id": doc_id, **deepcopy(doc)} if doc is not None else None

    def add(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = uuid.uuid4().hex[:20]
        self._col(collection)[doc_id] = deepcopy(data)
        return {"id": doc_id, **data}

    def set(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self._col(collection)[doc_id] = deepcopy(data)

    def update(self, collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        col = self._col(collection)
        if doc_id not in col:
            return None
        col[doc_id].update(deepcopy(data))
        return self.get(collection, doc_id)

    def delete(self, collection: str, doc_id: str) -> bool:
        return self._col(collection).pop(doc_id, None) is not None

    def add_many(self, collection: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.add(collection, item) for item in items]

    def delete_many(self, collection: str, doc_ids: list[str]) -> int:
        return sum(self.delete(collection, d) for d in doc_ids)


def _load_credentials():
    from firebase_admin import credentials

    if config.FIREBASE_SERVICE_ACCOUNT_JSON:
        return credentials.Certificate(json.loads(config.FIREBASE_SERVICE_ACCOUNT_JSON))
    if config.FIREBASE_SERVICE_ACCOUNT_PATH:
        return credentials.Certificate(config.FIREBASE_SERVICE_ACCOUNT_PATH)
    return None


def _load_sample_csv(target: MemoryRepo) -> None:
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "fx_krw.csv"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        target.add_many(
            DATA_COLLECTION,
            [
                {"date": r["date"], "currency": r["currency"], "value": float(r["value"]), "memo": r["memo"]}
                for r in csv.DictReader(f)
            ],
        )


def _create_repo():
    try:
        cred = _load_credentials()
    except Exception:
        logger.exception("Firebase 서비스 계정 정보를 읽지 못했습니다.")
        cred = None
    if cred is None:
        logger.warning("Firebase 자격 증명이 없어 메모리 저장소로 실행합니다(개발용, CSV 샘플 자동 로드).")
        mem = MemoryRepo()
        _load_sample_csv(mem)
        return mem

    import firebase_admin
    from firebase_admin import firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return FirestoreRepo(firestore.client())


repo = _create_repo()
