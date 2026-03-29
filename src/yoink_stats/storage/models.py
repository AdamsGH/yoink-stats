"""Stats plugin ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, DateTime, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.types import NullType
from sqlalchemy.orm import Mapped, mapped_column

from yoink.core.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(Base):
    """Every message in a monitored group, including service messages."""
    __tablename__ = "stats_messages"
    __table_args__ = (
        Index("idx_stats_msg_chat_date", "chat_id", "date"),
        Index("idx_stats_msg_user_date", "from_user", "date"),
        Index("idx_stats_msg_type", "msg_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    from_user: Mapped[int | None] = mapped_column(BigInteger)
    reply_to_message: Mapped[int | None] = mapped_column(BigInteger)
    forward_from: Mapped[int | None] = mapped_column(BigInteger)
    forward_from_chat: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    msg_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    sticker_set_name: Mapped[str | None] = mapped_column(String(128))
    new_chat_title: Mapped[str | None] = mapped_column(String(256))
    file_id: Mapped[str | None] = mapped_column(String(256))
    is_edited: Mapped[bool] = mapped_column(__import__("sqlalchemy").Boolean, default=False, nullable=False)
    sender_tag: Mapped[str | None] = mapped_column(String(64))
    text_search: Mapped[None] = mapped_column(TSVECTOR, nullable=True, index=False)


class UserEvent(Base):
    """Join/leave/pin events in a monitored group."""
    __tablename__ = "stats_user_events"
    __table_args__ = (
        Index("idx_stats_ue_chat_date", "chat_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)


class GroupMember(Base):
    """Known membership state of a user in a group, updated by sync."""
    __tablename__ = "stats_group_members"
    __table_args__ = (
        __import__("sqlalchemy").Index("idx_sgm_chat_user", "chat_id", "user_id"),
        __import__("sqlalchemy").UniqueConstraint("chat_id", "user_id", name="uq_sgm_chat_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    in_chat: Mapped[bool] = mapped_column(__import__("sqlalchemy").Boolean, nullable=False, default=True)
    status: Mapped[str | None] = mapped_column(String(32))
    joined_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class Reaction(Base):
    """Per-user reactions on messages in monitored groups."""
    __tablename__ = "stats_reactions"
    __table_args__ = (
        __import__("sqlalchemy").Index("idx_stats_reactions_user_chat", "user_id", "chat_id"),
        __import__("sqlalchemy").Index("idx_stats_reactions_chat_date", "chat_id", "date"),
        __import__("sqlalchemy").UniqueConstraint("user_id", "chat_id", "message_id", "reaction_key", name="uq_stats_reactions_user_msg_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reaction_key: Mapped[str] = mapped_column(String(64), nullable=False)
    reaction_type: Mapped[str] = mapped_column(String(16), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class UserNameHistory(Base):
    """Username/display-name history per user, temporal log."""
    __tablename__ = "stats_user_names"
    __table_args__ = (
        Index("idx_stats_un_user_date", "user_id", "date"),
        UniqueConstraint("user_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(256))
