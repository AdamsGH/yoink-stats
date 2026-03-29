"""Message listener: logs every group message to the stats DB."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Message, Update, ReactionTypeEmoji, ReactionTypeCustomEmoji
from telegram.ext import Application, ContextTypes, MessageHandler, MessageReactionHandler, filters

logger = logging.getLogger(__name__)


def _classify_message(msg: Message) -> str:
    if msg.sticker:
        return "sticker"
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.animation:
        return "animation"
    if msg.voice:
        return "voice"
    if msg.audio:
        return "audio"
    if msg.document:
        return "document"
    if msg.video_note:
        return "video_note"
    if msg.poll:
        return "poll"
    if msg.location:
        return "location"
    if msg.game:
        return "game"
    if msg.new_chat_members:
        return "new_chat_members"
    if msg.left_chat_member:
        return "left_chat_member"
    if msg.new_chat_title:
        return "new_chat_title"
    if msg.new_chat_photo:
        return "new_chat_photo"
    if msg.pinned_message:
        return "pinned_message"
    return "text"


def _message_to_kwargs(msg: Message) -> dict:
    forward_from: int | None = None
    forward_from_chat: int | None = None
    if hasattr(msg, "forward_origin") and msg.forward_origin is not None:
        origin = msg.forward_origin
        sender = getattr(origin, "sender_user", None)
        if sender is not None:
            forward_from = sender.id
        sender_chat = getattr(origin, "sender_chat", None) or getattr(origin, "chat", None)
        if sender_chat is not None:
            forward_from_chat = sender_chat.id

    file_id: str | None = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.video:
        file_id = msg.video.file_id
    elif msg.document:
        file_id = msg.document.file_id
    elif msg.sticker:
        file_id = msg.sticker.file_id
    elif msg.audio:
        file_id = msg.audio.file_id
    elif msg.voice:
        file_id = msg.voice.file_id
    elif msg.video_note:
        file_id = msg.video_note.file_id
    elif msg.animation:
        file_id = msg.animation.file_id

    # sender_tag: tag or custom title of the sender (Bot API 9.5, supergroups only)
    sender_tag: str | None = getattr(msg, "sender_tag", None) or None

    # message_thread_id: forum topic ID (supergroups with topics enabled)
    message_thread_id: int | None = None
    if getattr(msg, "is_topic_message", False):
        message_thread_id = getattr(msg, "message_thread_id", None)

    return {
        "message_id": msg.message_id,
        "chat_id": msg.chat_id,
        "date": msg.date,
        "from_user": msg.from_user.id if msg.from_user else None,
        "reply_to_message": (
            msg.reply_to_message.message_id if msg.reply_to_message else None
        ),
        "forward_from": forward_from,
        "forward_from_chat": forward_from_chat,
        "text": msg.text,
        "caption": msg.caption,
        "msg_type": _classify_message(msg),
        "sticker_set_name": msg.sticker.set_name if msg.sticker else None,
        "new_chat_title": msg.new_chat_title,
        "file_id": file_id,
        "is_edited": False,
        "sender_tag": sender_tag,
        "message_thread_id": message_thread_id,
    }


async def _check_group_enabled(chat, context) -> bool:
    """Return True if stats should be recorded for this chat.

    If the group is not yet in the DB (bot was added to an existing chat),
    auto-register it as enabled so messages start being collected immediately.
    Returns False only when the group is explicitly disabled.
    """
    group_repo = context.bot_data.get("group_repo")
    if group_repo is None:
        return True
    try:
        group = await group_repo.get(chat.id)
        if group is None:
            await group_repo.upsert(group_id=chat.id, title=chat.title or str(chat.id))
            return True
        return group.enabled
    except Exception as exc:
        logger.debug("group_repo check failed for %d: %s", chat.id, exc)
        return False


async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg:
        return

    chat = msg.chat
    if chat.type not in ("group", "supergroup"):
        return

    if not await _check_group_enabled(chat, context):
        return

    msg_repo = context.bot_data.get("stats_message_repo")
    event_repo = context.bot_data.get("stats_event_repo")
    name_repo = context.bot_data.get("stats_name_repo")

    if msg_repo is None:
        return

    kwargs = _message_to_kwargs(msg)
    try:
        await msg_repo.log_message(**kwargs)
    except Exception as exc:
        logger.warning("Failed to log message %d in %d: %s", msg.message_id, chat.id, exc)
        return

    if msg.from_user and name_repo is not None:
        user = msg.from_user
        display = " ".join(filter(None, [user.first_name, user.last_name])) or None
        try:
            await name_repo.upsert(user.id, user.username, display)
        except Exception as exc:
            logger.debug("Failed to upsert username for %d: %s", user.id, exc)

    if event_repo is None:
        return

    if msg.new_chat_members:
        for member in msg.new_chat_members:
            try:
                await event_repo.log_event(
                    message_id=msg.message_id,
                    chat_id=chat.id,
                    user_id=member.id,
                    date=msg.date,
                    event="joined",
                )
            except Exception as exc:
                logger.debug("Failed to log join event for %d: %s", member.id, exc)
            if name_repo is not None:
                display = " ".join(filter(None, [member.first_name, member.last_name])) or None
                try:
                    await name_repo.upsert(member.id, member.username, display)
                except Exception as exc:
                    logger.debug("Failed to upsert name for new member %d: %s", member.id, exc)

    elif msg.left_chat_member:
        member = msg.left_chat_member
        try:
            await event_repo.log_event(
                message_id=msg.message_id,
                chat_id=chat.id,
                user_id=member.id,
                date=msg.date,
                event="left",
            )
        except Exception as exc:
            logger.debug("Failed to log leave event for %d: %s", member.id, exc)


async def log_edited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.edited_message
    if not msg:
        return

    chat = msg.chat
    if chat.type not in ("group", "supergroup"):
        return

    if not await _check_group_enabled(chat, context):
        return

    msg_repo = context.bot_data.get("stats_message_repo")
    if msg_repo is None:
        return

    updates: dict = {}
    if msg.text is not None:
        updates["text"] = msg.text
    if msg.caption is not None:
        updates["caption"] = msg.caption

    try:
        await msg_repo.update_message(chat.id, msg.message_id, **updates)
    except Exception as exc:
        logger.warning("Failed to update edited message %d in %d: %s", msg.message_id, chat.id, exc)


def _reaction_key(reaction) -> tuple[str, str] | None:
    """Return (reaction_key, reaction_type) for a reaction object, or None to skip."""
    if isinstance(reaction, ReactionTypeEmoji):
        return reaction.emoji, "emoji"
    if isinstance(reaction, ReactionTypeCustomEmoji):
        return reaction.custom_emoji_id, "custom_emoji"
    # ReactionTypePaid or unknown — track as "paid"
    rtype = getattr(reaction, "type", None)
    if rtype == "paid":
        return "paid", "paid"
    return None


async def log_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction_update = update.message_reaction
    if not reaction_update:
        return

    user = reaction_update.user
    if user is None:
        return

    chat = reaction_update.chat
    if chat.type not in ("group", "supergroup"):
        return

    if not await _check_group_enabled(chat, context):
        return

    reaction_repo = context.bot_data.get("stats_reaction_repo")
    if reaction_repo is None:
        return

    old_keys = {_reaction_key(r) for r in (reaction_update.old_reaction or [])} - {None}
    new_keys = {_reaction_key(r) for r in (reaction_update.new_reaction or [])} - {None}

    to_add = new_keys - old_keys
    to_remove = old_keys - new_keys

    now = datetime.now(timezone.utc)

    for key, rtype in to_add:
        try:
            await reaction_repo.upsert(
                user_id=user.id,
                chat_id=chat.id,
                message_id=reaction_update.message_id,
                reaction_key=key,
                reaction_type=rtype,
                date=now,
            )
        except Exception as exc:
            logger.debug("Failed to upsert reaction %s for user %d: %s", key, user.id, exc)

    for key, rtype in to_remove:
        try:
            await reaction_repo.delete(
                user_id=user.id,
                chat_id=chat.id,
                message_id=reaction_update.message_id,
                reaction_key=key,
            )
        except Exception as exc:
            logger.debug("Failed to delete reaction %s for user %d: %s", key, user.id, exc)


def register(app: Application) -> None:
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, log_message),
        group=100,
    )
    app.add_handler(
        MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS, log_edited),
        group=100,
    )
    app.add_handler(
        MessageReactionHandler(log_reaction),
        group=100,
    )
