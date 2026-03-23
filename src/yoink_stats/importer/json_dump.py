"""
Import Telegram Desktop chat history export (result.json) into stats_messages.

Usage:
    yoink-stats-import --json /path/to/result.json --db postgresql+asyncpg://... --chat-id -100123

The JSON file is the export from Telegram Desktop:
    Settings → Advanced → Export Telegram Data → select a chat → Machine-readable JSON
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MEDIA_TYPE_MAP: dict[str, str] = {
    "animation":   "animation",
    "audio_file":  "audio",
    "video_file":  "video",
    "voice_message": "voice",
    "video_message": "video_note",
    "sticker":     "sticker",
    "document":    "document",
}


def _text_content(raw: Any) -> str:
    """Flatten Telegram's mixed text/entity list into a plain string."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def _parse_date(s: str) -> datetime:
    """Parse ISO date string from Telegram export into UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_message(msg: dict, chat_id: int) -> tuple[dict | None, list[dict]]:
    """
    Convert one message dict from Telegram export to (message_kwargs, [event_kwargs]).
    Returns (None, []) if message should be skipped.
    """
    events: list[dict] = []

    msg_id = msg.get("id")
    raw_date = msg.get("date")
    if not msg_id or not raw_date:
        return None, []

    date = _parse_date(raw_date)
    msg_type = msg.get("type")

    base: dict[str, Any] = {
        "message_id": msg_id,
        "chat_id": chat_id,
        "date": date,
        "from_user": None,
        "reply_to_message": msg.get("reply_to_message_id"),
        "forward_from": None,
        "forward_from_chat": None,
        "text": None,
        "caption": None,
        "msg_type": None,
        "sticker_set_name": None,
        "new_chat_title": None,
        "file_id": None,
        "is_edited": False,
    }

    if msg_type == "message":
        from_id = msg.get("from_id", "")
        if isinstance(from_id, str) and from_id.startswith("user"):
            try:
                base["from_user"] = int(from_id[4:])
            except ValueError:
                pass

        forwarded_from = msg.get("forwarded_from")
        if forwarded_from:
            fwd_id = msg.get("from_id", "")
            if isinstance(fwd_id, str) and fwd_id.startswith("user"):
                try:
                    base["forward_from"] = int(fwd_id[4:])
                except ValueError:
                    pass

        raw_text = msg.get("text", "")
        text = _text_content(raw_text)

        photo = msg.get("photo")
        media_type = msg.get("media_type")
        file_val = msg.get("file", "")
        sticker_emoji = msg.get("sticker_emoji")

        if photo:
            base["msg_type"] = "photo"
            if text:
                base["caption"] = text
        elif media_type:
            base["msg_type"] = MEDIA_TYPE_MAP.get(media_type, media_type)
            if text:
                base["caption"] = text
            if media_type == "sticker" and file_val and ".webp" not in file_val:
                base["file_id"] = file_val
            if sticker_emoji:
                base["sticker_set_name"] = sticker_emoji
        elif text:
            base["msg_type"] = "text"
            base["text"] = text
        elif msg.get("poll"):
            base["msg_type"] = "poll"
        else:
            return None, []

    elif msg_type == "service":
        actor_id = msg.get("actor_id", "")
        if isinstance(actor_id, str) and actor_id.startswith("user"):
            try:
                base["from_user"] = int(actor_id[4:])
            except ValueError:
                pass

        action = msg.get("action", "")
        if action == "edit_group_title":
            base["msg_type"] = "new_chat_title"
            base["new_chat_title"] = msg.get("title")
        elif action == "pin_message":
            base["msg_type"] = "pinned_message"
        elif action == "edit_group_photo":
            base["msg_type"] = "new_chat_photo"
        elif action in ("invite_members", "join_group_by_link"):
            base["msg_type"] = "new_chat_members"
            members = msg.get("members") or []
            if members:
                for member_id in members:
                    uid = None
                    if isinstance(member_id, str) and member_id.startswith("user"):
                        try:
                            uid = int(member_id[4:])
                        except ValueError:
                            pass
                    elif isinstance(member_id, int):
                        uid = member_id
                    if uid:
                        events.append({
                            "message_id": msg_id,
                            "chat_id": chat_id,
                            "user_id": uid,
                            "date": date,
                            "event": "joined",
                        })
            elif base["from_user"]:
                events.append({
                    "message_id": msg_id,
                    "chat_id": chat_id,
                    "user_id": base["from_user"],
                    "date": date,
                    "event": "joined",
                })
        elif action == "remove_members":
            base["msg_type"] = "left_chat_member"
            for member_id in (msg.get("members") or []):
                uid = None
                if isinstance(member_id, str) and member_id.startswith("user"):
                    try:
                        uid = int(member_id[4:])
                    except ValueError:
                        pass
                elif isinstance(member_id, int):
                    uid = member_id
                if uid:
                    events.append({
                        "message_id": msg_id,
                        "chat_id": chat_id,
                        "user_id": uid,
                        "date": date,
                        "event": "left",
                    })
        else:
            base["msg_type"] = action or "service"
    else:
        return None, []

    if base["msg_type"] is None:
        return None, []

    return base, events


async def import_json(
    json_path: str | Path,
    db_url: str,
    chat_id: int,
    tz: str = "UTC",
    batch_size: int = 500,
    progress_cb: "Callable[[int, int], None] | None" = None,
) -> dict[str, int]:
    """
    Parse result.json and bulk-insert into stats_messages / stats_user_events.
    Skips messages already present (by message_id + chat_id).
    Returns {"inserted": N, "skipped": M, "events": K}.
    """
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from yoink_stats.storage.models import ChatMessage, UserEvent

    path = Path(json_path)
    logger.info("Loading %s", path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    messages_raw: list[dict] = data.get("messages", [])
    logger.info("Found %d raw messages", len(messages_raw))

    if not messages_raw:
        return {"inserted": 0, "skipped": 0, "events": 0}

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        existing = set(
            row[0]
            for row in (
                await session.execute(
                    select(ChatMessage.message_id).where(ChatMessage.chat_id == chat_id)
                )
            ).all()
        )

    logger.info("Already in DB: %d messages for chat_id=%d", len(existing), chat_id)

    to_insert: list[dict] = []
    to_insert_events: list[dict] = []
    user_names: dict[int, str] = {}
    skipped = 0

    for msg in messages_raw:
        kwargs, events = _parse_message(msg, chat_id)
        if kwargs is None:
            skipped += 1
            continue

        uid = kwargs.get("from_user")
        from_name = msg.get("from")
        if uid and from_name and uid not in user_names:
            user_names[uid] = from_name

        if kwargs["message_id"] in existing:
            skipped += 1
            continue
        to_insert.append(kwargs)
        to_insert_events.extend(events)

    logger.info("Inserting %d messages, %d events", len(to_insert), len(to_insert_events))

    inserted = 0
    total = len(to_insert)
    async with session_factory() as session:
        for i in range(0, total, batch_size):
            batch = to_insert[i : i + batch_size]
            session.add_all([ChatMessage(**kw) for kw in batch])
            await session.commit()
            inserted += len(batch)
            logger.info("  inserted %d / %d", inserted, total)
            if progress_cb:
                progress_cb(inserted, total)

    events_inserted = 0
    if to_insert_events:
        async with session_factory() as session:
            for i in range(0, len(to_insert_events), batch_size):
                batch = to_insert_events[i : i + batch_size]
                session.add_all([UserEvent(**kw) for kw in batch])
                await session.commit()
                events_inserted += len(batch)

    if user_names:
        from yoink_stats.storage.models import UserNameHistory
        async with session_factory() as session:
            existing_names = set(
                row[0]
                for row in (
                    await session.execute(
                        select(UserNameHistory.user_id).where(
                            UserNameHistory.user_id.in_(list(user_names.keys()))
                        )
                    )
                ).all()
            )
            new_names = [
                UserNameHistory(user_id=uid, display_name=name)
                for uid, name in user_names.items()
                if uid not in existing_names
            ]
            if new_names:
                session.add_all(new_names)
                await session.commit()
                logger.info("Saved %d user display names from import", len(new_names))

    await engine.dispose()
    return {"inserted": inserted, "skipped": skipped, "events": events_inserted}


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Import Telegram Desktop JSON export into yoink-stats DB")
    parser.add_argument("--json", required=True, help="Path to result.json")
    parser.add_argument("--db", required=True, help="Async SQLAlchemy DB URL (postgresql+asyncpg://...)")
    parser.add_argument("--chat-id", required=True, type=int, help="Telegram chat_id to associate messages with")
    parser.add_argument("--tz", default="UTC", help="Timezone for naive dates (default: UTC)")
    parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default: 500)")
    args = parser.parse_args()

    result = asyncio.run(import_json(
        json_path=args.json,
        db_url=args.db,
        chat_id=args.chat_id,
        tz=args.tz,
        batch_size=args.batch_size,
    ))
    print(f"Done: inserted={result['inserted']} skipped={result['skipped']} events={result['events']}")


if __name__ == "__main__":
    main()
