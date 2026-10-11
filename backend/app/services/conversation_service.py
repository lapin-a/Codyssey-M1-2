"""대화 기록 저장/조회."""
from datetime import datetime, timezone

from ..db import CONVERSATIONS_COLLECTION, repo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _brief(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "title": doc.get("title", ""),
        "message_count": len(doc.get("messages", [])),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def list_conversations() -> list[dict]:
    docs = repo.list(CONVERSATIONS_COLLECTION)
    docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return [_brief(d) for d in docs]


def get_conversation(conv_id: str) -> dict | None:
    doc = repo.get(CONVERSATIONS_COLLECTION, conv_id)
    if doc is None:
        return None
    return {**_brief(doc), "messages": doc.get("messages", [])}


def create_conversation(title: str, messages: list[dict]) -> dict:
    now = _now()
    for m in messages:
        m.setdefault("created_at", now)
        if m.get("created_at") is None:
            m["created_at"] = now
    doc = repo.add(
        CONVERSATIONS_COLLECTION,
        {"title": title, "messages": messages, "created_at": now, "updated_at": now},
    )
    return {**_brief(doc), "messages": doc["messages"]}


def append_messages(conv_id: str, new_messages: list[dict]) -> dict | None:
    doc = repo.get(CONVERSATIONS_COLLECTION, conv_id)
    if doc is None:
        return None
    messages = doc.get("messages", []) + new_messages
    return repo.update(CONVERSATIONS_COLLECTION, conv_id, {"messages": messages, "updated_at": _now()})


def delete_conversation(conv_id: str) -> bool:
    return repo.delete(CONVERSATIONS_COLLECTION, conv_id)
