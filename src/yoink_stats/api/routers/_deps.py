"""Shared dependencies, type aliases and helpers for stats routers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import ChatMemberLeft, ChatMemberBanned
from telegram.error import TelegramError

from yoink.core.auth.rbac import role_gte
from yoink.core.db.models import User, UserGroupPolicy, UserRole

ChatIdQuery = Annotated[int, Query(description="Telegram chat_id (negative for groups, e.g. -1001234567890)")]
DaysQuery = Annotated[int | None, Query(ge=1, le=3650, description="Limit results to last N days. Omit for all-time.")]
OffsetQuery = Annotated[int, Query(ge=0, description="Pagination offset")]
LimitQuery = Annotated[int, Query(ge=1, le=200, description="Max records to return")]

_STOPWORDS = frozenset([
    "the", "a", "an", "in", "on", "at", "to", "of", "is", "it",
    "and", "or", "but", "for", "with",
])


def _since_param(days: int | None) -> datetime | None:
    """Convert a days lookback window to an absolute UTC cutoff, or None for all-time."""
    if days is None or days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _is_chat_member(bot, chat_id: int, user_id: int) -> bool:
    """Return True if user is an active member of the chat.

    Returns False for ChatMemberLeft / ChatMemberBanned, or on any API error.
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return not isinstance(member, (ChatMemberLeft, ChatMemberBanned))
    except TelegramError:
        return False


async def _check_group_access(
    chat_id: int,
    session: AsyncSession,
    current_user: User,
    request=None,
) -> None:
    """Raise 403 if current_user is not allowed to read stats for chat_id.

    Admins/owners have unrestricted access.
    Moderators must have a UserGroupPolicy entry.
    Regular users pass getChatMember check; falls back to checking recorded messages.
    """
    if role_gte(current_user.role, UserRole.admin):
        return

    if role_gte(current_user.role, UserRole.moderator):
        policy = (await session.execute(
            select(UserGroupPolicy).where(
                UserGroupPolicy.user_id == current_user.id,
                UserGroupPolicy.group_id == chat_id,
            )
        )).scalar_one_or_none()
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this group",
            )
        return

    bot = getattr(getattr(request, "app", None), "state", None)
    bot = getattr(bot, "bot", None) if bot is not None else None

    if bot is not None:
        is_member = await _is_chat_member(bot, chat_id, current_user.id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this group",
            )
        return

    # Fallback when bot is unavailable (standalone API mode)
    from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415
    has_messages = (await session.execute(
        select(ChatMessage.id).where(
            ChatMessage.chat_id == chat_id,
            ChatMessage.from_user == current_user.id,
        ).limit(1)
    )).scalar_one_or_none()
    if has_messages is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )
