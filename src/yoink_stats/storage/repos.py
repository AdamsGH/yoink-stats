"""Stats plugin repositories."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.storage.models import ChatMessage, UserEvent, UserNameHistory


class MessageRepo:
    def __init__(self, sf: async_sessionmaker) -> None:
        self._sf = sf

    async def log_message(self, **kwargs: Any) -> ChatMessage:
        async with self._sf() as s:
            msg = ChatMessage(**kwargs)
            s.add(msg)
            await s.commit()
            await s.refresh(msg)
            return msg

    async def update_message(self, chat_id: int, message_id: int, **kwargs: Any) -> None:
        async with self._sf() as s:
            result = await s.execute(
                select(ChatMessage).where(
                    ChatMessage.chat_id == chat_id,
                    ChatMessage.message_id == message_id,
                )
            )
            msg = result.scalar_one_or_none()
            if msg is not None:
                for k, v in kwargs.items():
                    setattr(msg, k, v)
                msg.is_edited = True
                await s.commit()

    async def count_by_user(self, chat_id: int, limit: int = 20) -> list[tuple[int, int]]:
        async with self._sf() as s:
            result = await s.execute(
                select(ChatMessage.from_user, func.count(ChatMessage.id).label("cnt"))
                .where(ChatMessage.chat_id == chat_id, ChatMessage.from_user.isnot(None))
                .group_by(ChatMessage.from_user)
                .order_by(__import__("sqlalchemy").desc("cnt"))
                .limit(limit)
            )
            return [(row.from_user, row.cnt) for row in result]

    async def total_messages(self, chat_id: int) -> int:
        async with self._sf() as s:
            result = await s.execute(
                select(func.count(ChatMessage.id)).where(ChatMessage.chat_id == chat_id)
            )
            return result.scalar_one()


class UserEventRepo:
    def __init__(self, sf: async_sessionmaker) -> None:
        self._sf = sf

    async def log_event(self, **kwargs: Any) -> UserEvent:
        async with self._sf() as s:
            ev = UserEvent(**kwargs)
            s.add(ev)
            await s.commit()
            await s.refresh(ev)
            return ev


class UserNameRepo:
    def __init__(self, sf: async_sessionmaker) -> None:
        self._sf = sf

    async def upsert(
        self,
        user_id: int,
        username: str | None,
        display_name: str | None,
    ) -> None:
        async with self._sf() as s:
            result = await s.execute(
                select(UserNameHistory)
                .where(UserNameHistory.user_id == user_id)
                .order_by(UserNameHistory.date.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest and latest.username == username and latest.display_name == display_name:
                return
            s.add(UserNameHistory(
                user_id=user_id,
                date=datetime.now(timezone.utc),
                username=username,
                display_name=display_name,
            ))
            await s.commit()

    async def get_current(self, user_id: int) -> UserNameHistory | None:
        async with self._sf() as s:
            result = await s.execute(
                select(UserNameHistory)
                .where(UserNameHistory.user_id == user_id)
                .order_by(UserNameHistory.date.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_all_user_ids(self) -> list[int]:
        async with self._sf() as s:
            result = await s.execute(
                select(UserNameHistory.user_id).distinct()
            )
            return [row[0] for row in result]
