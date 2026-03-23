"""Periodic job to refresh username records for all known group members."""
from __future__ import annotations

import logging

from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def _get_enabled_group_ids(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    """Return chat_ids that appear in stats_messages and belong to enabled groups."""
    from sqlalchemy import select, distinct
    from yoink_stats.storage.models import ChatMessage
    from yoink.core.db.models import Group

    sf = context.bot_data.get("session_factory") or context.bot_data.get("stats_session_factory")
    if sf is None:
        group_repo = context.bot_data.get("group_repo")
        if group_repo is None:
            return []
        msg_repo = context.bot_data.get("stats_message_repo")
        if msg_repo is None:
            return []
        async with msg_repo._sf() as session:
            result = await session.execute(select(distinct(ChatMessage.chat_id)))
            all_chat_ids: list[int] = [row[0] for row in result]
        enabled: list[int] = []
        for cid in all_chat_ids:
            try:
                if await group_repo.is_enabled(cid):
                    enabled.append(cid)
            except Exception:
                pass
        return enabled

    msg_repo = context.bot_data.get("stats_message_repo")
    if msg_repo is None:
        return []
    async with msg_repo._sf() as session:
        result = await session.execute(
            select(distinct(ChatMessage.chat_id))
            .join(Group, Group.id == ChatMessage.chat_id)
            .where(Group.enabled.is_(True))
        )
        return [row[0] for row in result]


async def refresh_usernames(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh display names for all users visible in enabled groups."""
    name_repo = context.bot_data.get("stats_name_repo")
    msg_repo = context.bot_data.get("stats_message_repo")
    if name_repo is None or msg_repo is None:
        return

    from sqlalchemy import select, distinct
    from yoink_stats.storage.models import ChatMessage

    group_ids = await _get_enabled_group_ids(context)
    if not group_ids:
        logger.debug("No enabled groups found for username refresh")
        return

    async with msg_repo._sf() as session:
        result = await session.execute(
            select(distinct(ChatMessage.from_user)).where(
                ChatMessage.chat_id.in_(group_ids),
                ChatMessage.from_user.isnot(None),
            )
        )
        user_ids: list[int] = [row[0] for row in result]

    if not user_ids:
        logger.debug("No users to refresh")
        return

    refreshed = 0
    skipped = 0
    for user_id in user_ids:
        fetched = False
        for group_id in group_ids:
            try:
                member = await context.bot.get_chat_member(chat_id=group_id, user_id=user_id)
                user = member.user
                display = " ".join(filter(None, [user.first_name, user.last_name])) or None
                await name_repo.upsert(user_id, user.username, display)
                refreshed += 1
                fetched = True
                break
            except (BadRequest, Forbidden, TelegramError):
                continue
            except Exception:
                continue

        if not fetched:
            try:
                chat = await context.bot.get_chat(user_id)
                display = " ".join(filter(None, [chat.first_name, chat.last_name])) or None
                await name_repo.upsert(user_id, chat.username, display)
                refreshed += 1
            except Exception:
                skipped += 1

    logger.info("Username refresh complete: %d/%d refreshed, %d unreachable", refreshed, len(user_ids), skipped)
