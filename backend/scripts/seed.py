"""data/fx_krw.csv (5개 통화 × 10년, 약 1.3만 건)를 Firestore data 컬렉션에 넣고 스냅샷을 만든다.

주의: Firestore 무료 한도는 하루 쓰기 2만 회, 읽기 5만 회다. 한 번 적재에 쓰기 약 1.3만 회를 쓰므로
--force 재적재(읽기 1.3만 + 삭제 1.3만 + 쓰기 1.3만)는 하루 한도를 넘을 수 있다.

사용법 (backend 폴더에서):
    python -m scripts.seed                # 컬렉션이 비어 있을 때만 넣기
    python -m scripts.seed --force        # 기존 데이터를 지우고 다시 넣기
    python -m scripts.seed --snapshots    # 데이터는 그대로 두고 스냅샷만 다시 만들기(전체 읽기 1회)
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db import DATA_COLLECTION, repo
from app.services import data_service

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "fx_krw.csv"


def main():
    if repo.backend != "firestore":
        sys.exit("Firebase 자격 증명이 없습니다. .env 의 FIREBASE_SERVICE_ACCOUNT_* 를 설정하세요.")

    if "--snapshots" in sys.argv:
        data_service.rebuild_snapshots()
        print("스냅샷을 다시 만들었습니다.")
        return

    # 비어 있는지는 1건만 읽어서 확인한다
    has_data = any(True for _ in repo.client.collection(DATA_COLLECTION).limit(1).stream())
    if has_data and "--force" not in sys.argv:
        sys.exit("이미 데이터가 있습니다. 덮어쓰려면 --force 를 붙이세요.")
    if has_data:
        existing = repo.list(DATA_COLLECTION)
        repo.delete_many(DATA_COLLECTION, [d["id"] for d in existing])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = [
            {"date": r["date"], "currency": r["currency"], "value": float(r["value"]), "memo": r["memo"],
             "created_at": now, "updated_at": now}
            for r in csv.DictReader(f)
        ]
    saved = repo.add_many(DATA_COLLECTION, rows)
    data_service.rebuild_snapshots(saved)
    print(f"{len(saved)}개 데이터를 저장하고 스냅샷을 만들었습니다.")


if __name__ == "__main__":
    main()
