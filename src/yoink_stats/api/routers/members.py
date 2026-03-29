"""Members endpoints - chat member list, sync, chat-admin access."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_db
from yoink.core.auth.rbac import require_role, role_gte
from yoink.core.db.models import User, UserRole
from yoink.core.db.query import date_params, load_sql
from yoink_stats.api.routers._deps import ChatIdQuery, DaysQuery, _since_param
from yoink_stats.storage.models import ChatAdmin

_Q = Path(__file__).parent.parent.parent / "queries"
_SQL_MEMBERS = load_sql(_Q, "members")

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])




def _member_row_to_dict(row: object, cutoff: datetime) -> dict:
    last_active_at = getattr(row, "last_active_at", None)
    if last_active_at and last_active_at.year <= 1970:
        last_active_at = None
    return {
        "user_id": row.user_id,
        "display_name": row.display_name,
        "username": row.username,
        "has_photo": row.photo_url is not None,
        "message_count": row.message_count,
        "reaction_count": row.reaction_count,
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
        "last_active_at": last_active_at.isoformat() if last_active_at else None,
        "is_active": bool(last_active_at and last_active_at > cutoff),
        "in_chat": row.in_chat,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
    }


async def _sync_chat_admins(bot, chat_id: int, session: AsyncSession) -> None:
    """Fetch getChatAdministrators and upsert into stats_chat_admins."""
    try:
        admins = await bot.get_chat_administrators(chat_id=chat_id)
        now = datetime.now(timezone.utc)
        synced_ids: list[int] = []
        for member in admins:
            if member.user.is_bot:
                continue
            stmt = pg_insert(ChatAdmin).values(
                user_id=member.user.id,
                chat_id=chat_id,
                status=member.status,
                synced_at=now,
            ).on_conflict_do_update(
                index_elements=["user_id", "chat_id"],
                set_={"status": member.status, "synced_at": now},
            )
            await session.execute(stmt)
            synced_ids.append(member.user.id)
        if synced_ids:
            await session.execute(
                text("DELETE FROM stats_chat_admins WHERE chat_id = :chat_id AND user_id NOT IN :ids")
                .bindparams(chat_id=chat_id, ids=tuple(synced_ids))
            )
        await session.commit()
    except Exception:
        logger.exception("Failed to sync chat admins for chat_id=%s", chat_id)


async def _is_chat_admin_db(user_id: int, chat_id: int, session: AsyncSession) -> bool:
    row = await session.get(ChatAdmin, (user_id, chat_id))
    return row is not None


@router.get("/chat-admins", summary="List known chat admins")
async def stats_chat_admins(
    chat_id: ChatIdQuery,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    rows = (await session.execute(
        select(ChatAdmin).where(ChatAdmin.chat_id == chat_id)
    )).scalars().all()
    return [{"user_id": r.user_id, "status": r.status} for r in rows]


@router.get("/members", summary="Chat member activity list (chat admin or bot admin)")
async def stats_members(
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """All known users for this chat - message senders UNION synced members.

    Accessible to bot admins or users who are chat admins (checked via stats_chat_admins).
    Optional days window filters message_count, reaction_count and last_active_at.
    """
    if not role_gte(current_user.role, UserRole.admin):
        if not await _is_chat_admin_db(current_user.id, chat_id, session):
            raise HTTPException(status_code=403, detail="Not a chat admin")
        bot = getattr(getattr(request, "app", None), "state", None)
        bot = getattr(bot, "bot", None) if bot else None
        if bot and background_tasks is not None:
            background_tasks.add_task(_sync_chat_admins, bot, chat_id, session)

    since = _since_param(days)
    cutoff = since or (datetime.now(timezone.utc) - timedelta(days=90))
    rows = (await session.execute(text(_SQL_MEMBERS), date_params(since, chat_id=chat_id))).fetchall()
    return [_member_row_to_dict(row, cutoff) for row in rows]


@router.post("/members/sync", summary="Sync member list via user-mode session (admin+)")
async def stats_members_sync(
    chat_id: ChatIdQuery,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
) -> list[dict]:
    """Fetch all chat members via getChatMembers, write to stats_group_members,
    mark missing users as in_chat=false, then return merged member list."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert_core  # noqa: PLC0415
    from yoink.core.services.user_session import UserSessionError, UserSessionService  # noqa: PLC0415
    from yoink_stats.storage.models import GroupMember, UserNameHistory  # noqa: PLC0415

    svc: UserSessionService | None = None
    if hasattr(request.app.state, "bot_data"):
        svc = request.app.state.bot_data.get("user_session")
    if svc is None or not svc.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="User-mode session not available")

    all_members: list[dict] = []
    offset = 0
    page = 200
    while True:
        try:
            batch = await svc.get_chat_members(chat_id=chat_id, offset=offset, limit=page)
        except UserSessionError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        if not isinstance(batch, list):
            break
        all_members.extend(batch)
        if len(batch) < page:
            break
        offset += page

    now = datetime.now(timezone.utc)
    live_uids: set[int] = set()

    for m in all_members:
        user_obj = m.get("user") or {}
        uid = user_obj.get("id")
        if not uid:
            continue
        live_uids.add(uid)

        first_name: str | None = user_obj.get("first_name") or user_obj.get("firstName")
        username: str | None = user_obj.get("username")
        display_name: str | None = (
            " ".join(filter(None, [first_name, user_obj.get("last_name") or user_obj.get("lastName")])) or None
        )

        core_stmt = (
            pg_insert_core(User)
            .values(id=uid, first_name=first_name, username=username, role=UserRole.user)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"first_name": first_name, "username": username},
            )
        )
        await session.execute(core_stmt)

        if display_name or username:
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            name_stmt = (
                pg_insert_core(UserNameHistory)
                .values(user_id=uid, date=day, username=username, display_name=display_name)
                .on_conflict_do_update(
                    index_elements=["user_id", "date"],
                    set_={"username": username, "display_name": display_name},
                )
            )
            await session.execute(name_stmt)

        joined_ts = m.get("joined_date")
        joined_dt = datetime.fromtimestamp(joined_ts, tz=timezone.utc) if joined_ts else None

        stmt = (
            pg_insert(GroupMember)
            .values(chat_id=chat_id, user_id=uid, in_chat=True, status=m.get("status"), joined_date=joined_dt, synced_at=now)
            .on_conflict_do_update(
                constraint="uq_sgm_chat_user",
                set_={"in_chat": True, "status": m.get("status"), "joined_date": joined_dt, "synced_at": now},
            )
        )
        await session.execute(stmt)

    all_senders = (await session.execute(
        text("SELECT DISTINCT from_user FROM stats_messages WHERE chat_id = :chat_id AND from_user IS NOT NULL"),
        {"chat_id": chat_id},
    )).scalars().all()

    for uid in [u for u in all_senders if u not in live_uids]:
        stmt = (
            pg_insert(GroupMember)
            .values(chat_id=chat_id, user_id=uid, in_chat=False, status=None, joined_date=None, synced_at=now)
            .on_conflict_do_update(
                constraint="uq_sgm_chat_user",
                set_={"in_chat": False, "synced_at": now},
            )
        )
        await session.execute(stmt)

    await session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    rows = (await session.execute(text(_SQL_MEMBERS), date_params(None, chat_id=chat_id))).fetchall()
    return [_member_row_to_dict(row, cutoff) for row in rows]
