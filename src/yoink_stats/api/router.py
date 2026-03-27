"""Stats API routes - returns data for frontend recharts-based UI."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy import cast, func, select, text, distinct, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import ChatMemberLeft, ChatMemberBanned
from telegram.error import TelegramError

from yoink.core.api.deps import get_db
from yoink.core.auth.rbac import require_role, role_gte
from yoink.core.db.models import Group, User, UserGroupPolicy, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


async def _is_chat_member(bot, chat_id: int, user_id: int) -> bool:
    """Return True if user is an active member of the chat via getChatMember.

    Returns False for ChatMemberLeft / ChatMemberBanned, or on any API error
    (e.g. bot lacks admin rights in the group).
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
    request: Request | None = None,
) -> None:
    """
    Raise 403 if current_user is not allowed to read stats for chat_id.

    Admins and owners: unrestricted access.
    Moderators: must have a UserGroupPolicy entry (explicitly assigned).
    Regular users: getChatMember check (requires bot to be admin in the group);
                   if the bot lacks admin rights, falls back to checking whether
                   the user has any recorded messages in the chat.
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
    from yoink_stats.storage.models import ChatMessage
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

_STOPWORDS = frozenset([
    "the", "a", "an", "in", "on", "at", "to", "of", "is", "it",
    "and", "or", "but", "for", "with",
])


def _since_param(days: int | None) -> datetime | None:
    """Convert a days lookback window to an absolute UTC cutoff, or None for all-time."""
    if days is None or days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/groups", summary="List monitored groups with message counts")
async def stats_groups(
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """List monitored groups with message counts.

    Moderators see only groups they are members of.
    Admins and owners see all groups.
    """
    from yoink_stats.storage.models import ChatMessage

    q = (
        select(
            Group.id,
            Group.title,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.chat_id == Group.id)
        .where(Group.enabled.is_(True))
        .where(Group.id < 0)
        .group_by(Group.id, Group.title)
        .order_by(func.count(ChatMessage.id).desc())
    )

    if not role_gte(current_user.role, UserRole.admin):
        if role_gte(current_user.role, UserRole.moderator):
            # Moderators: explicitly assigned groups only
            q = q.where(
                Group.id.in_(
                    select(UserGroupPolicy.group_id).where(
                        UserGroupPolicy.user_id == current_user.id
                    )
                )
            )
        else:
            # Regular users: groups where they have at least one recorded message
            q = q.where(
                Group.id.in_(
                    select(ChatMessage.chat_id).where(
                        ChatMessage.from_user == current_user.id
                    ).distinct()
                )
            )

    rows = (await session.execute(q)).all()

    return [
        {
            "chat_id": row.id,
            "title": row.title,
            "message_count": row.message_count or 0,
        }
        for row in rows
    ]


@router.get("/overview", summary="Chat statistics overview")
async def stats_overview(
    request: Request,
    chat_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Overview: total messages, unique users, first/last message date."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage

    total = (await session.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.chat_id == chat_id)
    )).scalar_one()

    unique_users = (await session.execute(
        select(func.count(distinct(ChatMessage.from_user))).where(
            ChatMessage.chat_id == chat_id,
            ChatMessage.from_user.isnot(None),
        )
    )).scalar_one()

    date_range = (await session.execute(
        select(func.min(ChatMessage.date), func.max(ChatMessage.date)).where(
            ChatMessage.chat_id == chat_id
        )
    )).fetchone()

    return {
        "chat_id": chat_id,
        "total_messages": total,
        "unique_users": unique_users,
        "first_date": date_range[0].isoformat() if date_range and date_range[0] else None,
        "last_date": date_range[1].isoformat() if date_range and date_range[1] else None,
    }


@router.get("/top-users", summary="Top users by message count")
async def stats_top_users(
    request: Request,
    chat_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top message senders. Optional days window filters the message range."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id, "limit": limit}
    date_filter = "AND m.date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            m.from_user,
            COUNT(m.id) AS cnt,
            COALESCE(un.username, u.username) AS username,
            COALESCE(un.display_name, u.first_name) AS display_name
        FROM stats_messages m
        LEFT JOIN LATERAL (
            SELECT username, display_name
            FROM stats_user_names
            WHERE user_id = m.from_user
            ORDER BY date DESC
            LIMIT 1
        ) un ON TRUE
        LEFT JOIN users u ON u.id = m.from_user
        WHERE m.chat_id = :chat_id
          AND m.from_user IS NOT NULL
          {date_filter}
        GROUP BY m.from_user, un.username, un.display_name, u.username, u.first_name
        ORDER BY cnt DESC
        LIMIT :limit
    """), params)).fetchall()

    return [
        {
            "user_id": row.from_user,
            "username": row.username,
            "display_name": row.display_name,
            "count": row.cnt,
        }
        for row in rows
    ]


@router.get("/activity-by-hour", summary="Message activity distribution by hour of day")
async def stats_activity_by_hour(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by hour of day (0-23). Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage

    since = _since_param(days)
    hour_col = cast(func.extract("hour", ChatMessage.date), Integer).label("hour")
    q = (
        select(hour_col, func.count(ChatMessage.id).label("count"))
        .where(ChatMessage.chat_id == chat_id)
    )
    if since:
        q = q.where(ChatMessage.date >= since)
    rows = (await session.execute(q.group_by(hour_col).order_by(hour_col))).fetchall()

    data = {row.hour: row.count for row in rows}
    return [{"hour": h, "count": data.get(h, 0)} for h in range(24)]


@router.get("/activity-by-day", summary="Message activity distribution by day of week")
async def stats_activity_by_day(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by day of week (0=Mon, 6=Sun). Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT ((EXTRACT(DOW FROM date)::int + 6) % 7) AS dow, COUNT(id) AS cnt
        FROM stats_messages
        WHERE chat_id = :chat_id {date_filter}
        GROUP BY dow
        ORDER BY dow
    """), params)).fetchall()

    data = {int(row.dow): row.cnt for row in rows}
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [
        {"day": d, "day_name": day_names[d], "count": data.get(d, 0)}
        for d in range(7)
    ]


@router.get("/activity-by-week", summary="Weekly message volume over time")
async def stats_activity_by_week(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by day+hour for heatmap (day=0-6 Mon=0, hour=0-23). Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            ((EXTRACT(DOW FROM date)::int + 6) % 7) AS dow,
            EXTRACT(HOUR FROM date)::int AS hour,
            COUNT(id) AS cnt
        FROM stats_messages
        WHERE chat_id = :chat_id {date_filter}
        GROUP BY dow, hour
    """), params)).fetchall()

    return [
        {"day": int(row.dow), "hour": int(row.hour), "count": int(row.cnt)}
        for row in rows
    ]


@router.get("/message-types", summary="Breakdown of message types (text/photo/video/etc)")
async def stats_message_types(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message breakdown by type. Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage

    since = _since_param(days)
    cnt = func.count(ChatMessage.id).label("count")
    q = select(ChatMessage.msg_type, cnt).where(ChatMessage.chat_id == chat_id)
    if since:
        q = q.where(ChatMessage.date >= since)
    rows = (await session.execute(q.group_by(ChatMessage.msg_type).order_by(cnt.desc()))).fetchall()

    return [{"type": row.msg_type, "count": row.count} for row in rows]


@router.get("/history", summary="Daily message count history")
async def stats_history(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Daily message counts. If days is omitted, returns all history."""
    await _check_group_access(chat_id, session, current_user, request)

    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (await session.execute(text("""
            SELECT DATE(date AT TIME ZONE 'UTC') AS day, COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id AND date >= :since
            GROUP BY day
            ORDER BY day
        """), {"chat_id": chat_id, "since": since})).fetchall()
    else:
        rows = (await session.execute(text("""
            SELECT DATE(date AT TIME ZONE 'UTC') AS day, COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id
            GROUP BY day
            ORDER BY day
        """), {"chat_id": chat_id})).fetchall()

    return [{"date": str(row.day), "count": int(row.cnt)} for row in rows]


@router.get("/words", summary="Top words / word frequency")
async def stats_words(
    request: Request,
    chat_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top words from text messages. Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id, "limit": limit}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(rf"""
        WITH messages AS (
            SELECT COALESCE(text, '') || ' ' || COALESCE(caption, '') AS body
            FROM stats_messages
            WHERE chat_id = :chat_id
              AND (text IS NOT NULL OR caption IS NOT NULL)
              {date_filter}
        ),
        words AS (
            SELECT lower(regexp_replace(w, '[^\w]|[\d_]', '', 'g')) AS word
            FROM messages,
                 regexp_split_to_table(body, '\s+') AS w
            WHERE char_length(regexp_replace(w, '[^\w]|[\d_]', '', 'g')) >= 3
        )
        SELECT word, COUNT(*) AS cnt
        FROM words
        WHERE word NOT IN (
            'the','a','an','in','on','at','to','of','is','it','and','or',
            'but','for','with','это','как','что','так','все','там','уже',
            'мне','его','она','они','ещё','был','не','да','же','вот','то',
            'из','он','по','до','во','от','со','при','за','над','под','для'
        )
          AND word <> ''
        GROUP BY word
        ORDER BY cnt DESC
        LIMIT :limit
    """), params)).fetchall()

    return [{"word": row.word, "count": int(row.cnt)} for row in rows]


@router.get("/user-stats", summary="Per-user statistics breakdown")
async def stats_user(
    request: Request,
    chat_id: int = Query(...),
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Per-user stats: total, first/last date, avg/day, top type."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage, UserNameHistory

    summary = (await session.execute(text("""
        SELECT
            COUNT(id) AS total,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM stats_messages
        WHERE chat_id = :chat_id AND from_user = :user_id
    """), {"chat_id": chat_id, "user_id": user_id})).fetchone()

    if not summary or not summary.total:
        return {
            "user_id": user_id,
            "username": None,
            "display_name": None,
            "total": 0,
            "first_date": None,
            "last_date": None,
            "avg_per_day": 0.0,
            "top_type": None,
        }

    top_type_row = (await session.execute(text("""
        SELECT msg_type, COUNT(id) AS cnt
        FROM stats_messages
        WHERE chat_id = :chat_id AND from_user = :user_id
        GROUP BY msg_type
        ORDER BY cnt DESC
        LIMIT 1
    """), {"chat_id": chat_id, "user_id": user_id})).fetchone()

    name_row = (await session.execute(text("""
        SELECT username, display_name
        FROM stats_user_names
        WHERE user_id = :user_id
        ORDER BY date DESC
        LIMIT 1
    """), {"user_id": user_id})).fetchone()

    total = int(summary.total)
    first_date: datetime = summary.first_date
    last_date: datetime = summary.last_date
    span_days = max((last_date - first_date).days, 1)
    avg_per_day = round(total / span_days, 2)

    return {
        "user_id": user_id,
        "username": name_row.username if name_row else None,
        "display_name": name_row.display_name if name_row else None,
        "total": total,
        "first_date": first_date.isoformat() if first_date else None,
        "last_date": last_date.isoformat() if last_date else None,
        "avg_per_day": avg_per_day,
        "top_type": top_type_row.msg_type if top_type_row else None,
    }


@router.get("/activity-by-month", summary="Monthly message volume")
async def stats_activity_by_month(
    request: Request,
    chat_id: int = Query(...),
    year: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count per calendar month. Defaults to the last 12 months when year is omitted."""
    await _check_group_access(chat_id, session, current_user, request)
    if year is not None:
        rows = (await session.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', date), 'YYYY-MM') AS month,
                COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id
              AND EXTRACT(YEAR FROM date) = :year
            GROUP BY month
            ORDER BY month
        """), {"chat_id": chat_id, "year": year})).fetchall()
    else:
        since = datetime.now(timezone.utc) - timedelta(days=365)
        rows = (await session.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', date), 'YYYY-MM') AS month,
                COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id
              AND date >= :since
            GROUP BY month
            ORDER BY month
        """), {"chat_id": chat_id, "since": since})).fetchall()

    return [{"month": row.month, "count": int(row.cnt)} for row in rows]


@router.get("/ecdf", summary="Empirical CDF of messages per user")
async def stats_ecdf(
    request: Request,
    chat_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count distribution across users with cumulative percentages."""
    await _check_group_access(chat_id, session, current_user, request)
    rows = (await session.execute(text("""
        WITH per_user AS (
            SELECT
                m.from_user,
                COUNT(m.id) AS cnt,
                un.username,
                un.display_name
            FROM stats_messages m
            LEFT JOIN LATERAL (
                SELECT username, display_name
                FROM stats_user_names
                WHERE user_id = m.from_user
                ORDER BY date DESC
                LIMIT 1
            ) un ON TRUE
            WHERE m.chat_id = :chat_id
              AND m.from_user IS NOT NULL
            GROUP BY m.from_user, un.username, un.display_name
            ORDER BY cnt DESC
            LIMIT :limit
        ),
        total AS (
            SELECT SUM(cnt) AS grand_total FROM per_user
        )
        SELECT
            p.from_user,
            p.cnt,
            p.username,
            p.display_name,
            ROUND(
                SUM(p.cnt) OVER (ORDER BY p.cnt DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                * 100.0 / NULLIF(t.grand_total, 0),
                1
            ) AS cumulative_pct
        FROM per_user p, total t
        ORDER BY p.cnt DESC
    """), {"chat_id": chat_id, "limit": limit})).fetchall()

    return [
        {
            "user_id": row.from_user,
            "username": row.username,
            "display_name": row.display_name,
            "count": int(row.cnt),
            "cumulative_pct": float(row.cumulative_pct) if row.cumulative_pct is not None else None,
        }
        for row in rows
    ]


@router.get("/title-history", summary="Chat title change history")
async def stats_title_history(
    request: Request,
    chat_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """History of chat title changes."""
    await _check_group_access(chat_id, session, current_user, request)
    rows = (await session.execute(text("""
        SELECT
            m.date,
            m.new_chat_title,
            m.from_user,
            un.username,
            un.display_name
        FROM stats_messages m
        LEFT JOIN LATERAL (
            SELECT username, display_name
            FROM stats_user_names
            WHERE user_id = m.from_user
            ORDER BY date DESC
            LIMIT 1
        ) un ON TRUE
        WHERE m.chat_id = :chat_id
          AND m.msg_type = 'new_chat_title'
        ORDER BY m.date
    """), {"chat_id": chat_id})).fetchall()

    return [
        {
            "date": row.date.isoformat() if row.date else None,
            "title": row.new_chat_title,
            "changed_by_user_id": row.from_user,
            "changed_by_username": row.username,
        }
        for row in rows
    ]


@router.get("/mention-stats", summary="Mention frequency between users")
async def stats_mention_stats(
    request: Request,
    chat_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top @mentions extracted from text messages. Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id, "limit": limit}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT lower(m[1]) AS mention, COUNT(*) AS cnt
        FROM stats_messages,
             regexp_matches(COALESCE(text, ''), '@([a-zA-Z0-9_]{{4,}})', 'g') AS m
        WHERE chat_id = :chat_id {date_filter}
        GROUP BY mention
        ORDER BY cnt DESC
        LIMIT :limit
    """), params)).fetchall()

    return [{"mention": f"@{row.mention}", "count": int(row.cnt)} for row in rows]


@router.get("/daily-activity", summary="Daily active users (DAU) time series")
async def stats_daily_activity(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Per-day message count and unique active users (DAU). Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            DATE(date AT TIME ZONE 'UTC') AS day,
            COUNT(id) AS messages,
            COUNT(DISTINCT from_user) FILTER (WHERE from_user IS NOT NULL) AS dau
        FROM stats_messages
        WHERE chat_id = :chat_id {date_filter}
        GROUP BY day
        ORDER BY day
    """), params)).fetchall()

    return [
        {"date": str(row.day), "messages": int(row.messages), "dau": int(row.dau)}
        for row in rows
    ]


@router.get("/member-events", summary="Group join/leave events over time")
async def stats_member_events(
    request: Request,
    chat_id: int = Query(...),
    days: int | None = Query(None, ge=1, le=3650),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Daily join/leave counts from user events. Optional days window."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            DATE(date AT TIME ZONE 'UTC') AS day,
            COUNT(*) FILTER (WHERE event = 'joined') AS joined,
            COUNT(*) FILTER (WHERE event = 'left') AS left_count
        FROM stats_user_events
        WHERE chat_id = :chat_id {date_filter}
        GROUP BY day
        ORDER BY day
    """), params)).fetchall()

    return [
        {"date": str(row.day), "joined": int(row.joined), "left": int(row.left_count)}
        for row in rows
    ]


class ImportStatus(BaseModel):
    job_id: str
    status: str
    inserted: int = 0
    skipped: int = 0
    events: int = 0
    processed: int = 0
    total: int = 0
    error: str | None = None


_import_jobs: dict[str, ImportStatus] = {}


@router.post("/import", response_model=ImportStatus, summary="Import Telegram Desktop chat export (result.json)")
async def import_history(
    background_tasks: BackgroundTasks,
    chat_id: int = Query(..., description="Telegram chat_id to associate messages with"),
    file: UploadFile = File(..., description="Telegram Desktop result.json export"),
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """
    Upload a Telegram Desktop chat history export (result.json) and import it
    into the stats database. Runs in background, returns job_id to poll status.
    """
    import shutil
    import tempfile
    import uuid

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a .json export from Telegram Desktop")

    job_id = str(uuid.uuid4())
    _import_jobs[job_id] = ImportStatus(job_id=job_id, status="running")

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    try:
        shutil.copyfileobj(file.file, tmp)
    finally:
        tmp.close()

    async def _run(path: str, cid: int, jid: str) -> None:
        import os
        try:
            from yoink_stats.importer.json_dump import import_json
            from yoink.core.config import CoreSettings
            cfg = CoreSettings()

            def _progress(done: int, total: int) -> None:
                job = _import_jobs.get(jid)
                if job:
                    _import_jobs[jid] = ImportStatus(
                        job_id=jid,
                        status="running",
                        processed=done,
                        total=total,
                        inserted=job.inserted,
                        skipped=job.skipped,
                        events=job.events,
                    )

            result = await import_json(
                json_path=path, db_url=cfg.database_url, chat_id=cid,
                progress_cb=_progress,
            )
            total = result["inserted"] + result["skipped"]
            _import_jobs[jid] = ImportStatus(
                job_id=jid,
                status="done",
                inserted=result["inserted"],
                skipped=result["skipped"],
                events=result["events"],
                processed=total,
                total=total,
            )
        except Exception as exc:
            logger.exception("Import job %s failed", jid)
            _import_jobs[jid] = ImportStatus(job_id=jid, status="error", error=str(exc))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    background_tasks.add_task(_run, tmp.name, chat_id, job_id)
    return _import_jobs[job_id]


class ImportByPathRequest(BaseModel):
    path: str
    chat_id: int


@router.post("/import/by-path", response_model=ImportStatus, summary="Import from server-side file path (owner only)")
async def import_history_by_path(
    body: ImportByPathRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """Start import from a file path already on the server (no upload needed)."""
    import uuid
    from pathlib import Path

    p = Path(body.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {body.path}")

    job_id = str(uuid.uuid4())
    _import_jobs[job_id] = ImportStatus(job_id=job_id, status="running")

    async def _run(path: str, cid: int, jid: str) -> None:
        try:
            from yoink_stats.importer.json_dump import import_json
            from yoink.core.config import CoreSettings
            cfg = CoreSettings()

            def _progress(done: int, total: int) -> None:
                job = _import_jobs.get(jid)
                if job:
                    _import_jobs[jid] = ImportStatus(
                        job_id=jid, status="running",
                        processed=done, total=total,
                        inserted=job.inserted, skipped=job.skipped, events=job.events,
                    )

            result = await import_json(
                json_path=path, db_url=cfg.database_url, chat_id=cid,
                progress_cb=_progress,
            )
            _import_jobs[jid] = ImportStatus(
                job_id=jid, status="done",
                inserted=result["inserted"], skipped=result["skipped"], events=result["events"],
                processed=result["inserted"], total=result["inserted"],
            )
        except Exception as exc:
            logger.exception("Import by-path job %s failed", jid)
            _import_jobs[jid] = ImportStatus(job_id=jid, status="error", error=str(exc))

    background_tasks.add_task(_run, str(p), body.chat_id, job_id)
    return _import_jobs[job_id]


@router.get("/import/{job_id}", response_model=ImportStatus, summary="Get import job status")
async def import_status(
    job_id: str,
    current_user: User = Depends(require_role(UserRole.owner)),
) -> ImportStatus:
    """Poll the status of a running import job."""
    job = _import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
