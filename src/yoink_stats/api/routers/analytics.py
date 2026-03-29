"""Analytics endpoints - message stats, activity charts, word/mention frequency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import cast, func, select, text, distinct, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_db
from yoink.core.auth.rbac import require_role, role_gte
from yoink.core.db.models import Group, User, UserGroupPolicy, UserRole
from yoink_stats.api.routers._deps import (
    ChatIdQuery, DaysQuery, _check_group_access, _since_param,
)

router = APIRouter(tags=["stats"])


@router.get("/groups", summary="List monitored groups with message counts")
async def stats_groups(
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Moderators see only groups they are members of. Admins and owners see all groups."""
    from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415

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
            q = q.where(
                Group.id.in_(
                    select(UserGroupPolicy.group_id).where(
                        UserGroupPolicy.user_id == current_user.id
                    )
                )
            )
        else:
            q = q.where(
                Group.id.in_(
                    select(ChatMessage.chat_id).where(
                        ChatMessage.from_user == current_user.id
                    ).distinct()
                )
            )

    rows = (await session.execute(q)).all()
    return [{"chat_id": row.id, "title": row.title, "message_count": row.message_count or 0} for row in rows]


@router.get("/overview", summary="Chat statistics overview")
async def stats_overview(
    request: Request,
    chat_id: ChatIdQuery,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Overview: total messages, unique users, first/last message date, total reactions."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage, Reaction  # noqa: PLC0415

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

    total_reactions = (await session.execute(
        select(func.count(Reaction.id)).where(Reaction.chat_id == chat_id)
    )).scalar_one()

    return {
        "chat_id": chat_id,
        "total_messages": total,
        "unique_users": unique_users,
        "total_reactions": total_reactions,
        "first_date": date_range[0].isoformat() if date_range and date_range[0] else None,
        "last_date": date_range[1].isoformat() if date_range and date_range[1] else None,
    }


@router.get("/top-users", summary="Top users by message count")
async def stats_top_users(
    request: Request,
    chat_id: ChatIdQuery,
    limit: int = Query(20, ge=1, le=100),
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top message senders, optionally filtered by a days window."""
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
            COALESCE(un.display_name, u.first_name) AS display_name,
            u.photo_url
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
        GROUP BY m.from_user, un.username, un.display_name, u.username, u.first_name, u.photo_url
        ORDER BY cnt DESC
        LIMIT :limit
    """), params)).fetchall()

    return [
        {
            "user_id": row.from_user,
            "username": row.username,
            "display_name": row.display_name,
            "count": row.cnt,
            "has_photo": row.photo_url is not None,
        }
        for row in rows
    ]


@router.get("/activity-by-hour", summary="Message activity distribution by hour of day")
async def stats_activity_by_hour(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by hour of day (0-23)."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415

    since = _since_param(days)
    hour_col = cast(func.extract("hour", ChatMessage.date), Integer).label("hour")
    q = select(hour_col, func.count(ChatMessage.id).label("count")).where(ChatMessage.chat_id == chat_id)
    if since:
        q = q.where(ChatMessage.date >= since)
    rows = (await session.execute(q.group_by(hour_col).order_by(hour_col))).fetchall()

    data = {row.hour: row.count for row in rows}
    return [{"hour": h, "count": data.get(h, 0)} for h in range(24)]


@router.get("/activity-by-day", summary="Message activity distribution by day of week")
async def stats_activity_by_day(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by day of week (0=Mon, 6=Sun)."""
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
    return [{"day": d, "day_name": day_names[d], "count": data.get(d, 0)} for d in range(7)]


@router.get("/activity-by-week", summary="Weekly heatmap (day x hour)")
async def stats_activity_by_week(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count by day+hour for heatmap (day=0-6 Mon=0, hour=0-23)."""
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

    return [{"day": int(row.dow), "hour": int(row.hour), "count": int(row.cnt)} for row in rows]


@router.get("/message-types", summary="Breakdown of message types")
async def stats_message_types(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message breakdown by type (text/photo/video/etc)."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415

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
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
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
            GROUP BY day ORDER BY day
        """), {"chat_id": chat_id, "since": since})).fetchall()
    else:
        rows = (await session.execute(text("""
            SELECT DATE(date AT TIME ZONE 'UTC') AS day, COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id
            GROUP BY day ORDER BY day
        """), {"chat_id": chat_id})).fetchall()

    return [{"date": str(row.day), "count": int(row.cnt)} for row in rows]


@router.get("/words", summary="Top words / word frequency")
async def stats_words(
    request: Request,
    chat_id: ChatIdQuery,
    limit: int = Query(20, ge=1, le=100),
    days: DaysQuery = None,
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
    chat_id: ChatIdQuery,
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Per-user stats: total, first/last date, avg/day, top type, reaction count."""
    await _check_group_access(chat_id, session, current_user, request)

    summary = (await session.execute(text("""
        SELECT COUNT(id) AS total, MIN(date) AS first_date, MAX(date) AS last_date
        FROM stats_messages
        WHERE chat_id = :chat_id AND from_user = :user_id
    """), {"chat_id": chat_id, "user_id": user_id})).fetchone()

    reaction_row = (await session.execute(text("""
        SELECT COUNT(*) AS reaction_count
        FROM stats_reactions
        WHERE chat_id = :chat_id AND user_id = :user_id
    """), {"chat_id": chat_id, "user_id": user_id})).fetchone()
    reaction_count = int(reaction_row.reaction_count) if reaction_row else 0

    if not summary or not summary.total:
        return {
            "user_id": user_id, "username": None, "display_name": None,
            "total": 0, "reaction_count": reaction_count,
            "first_date": None, "last_date": None, "avg_per_day": 0.0, "top_type": None,
        }

    top_type_row = (await session.execute(text("""
        SELECT msg_type, COUNT(id) AS cnt
        FROM stats_messages
        WHERE chat_id = :chat_id AND from_user = :user_id
        GROUP BY msg_type ORDER BY cnt DESC LIMIT 1
    """), {"chat_id": chat_id, "user_id": user_id})).fetchone()

    name_row = (await session.execute(text("""
        SELECT username, display_name FROM stats_user_names
        WHERE user_id = :user_id ORDER BY date DESC LIMIT 1
    """), {"user_id": user_id})).fetchone()

    total = int(summary.total)
    first_date: datetime = summary.first_date
    last_date: datetime = summary.last_date
    span_days = max((last_date - first_date).days, 1)

    return {
        "user_id": user_id,
        "username": name_row.username if name_row else None,
        "display_name": name_row.display_name if name_row else None,
        "total": total,
        "reaction_count": reaction_count,
        "first_date": first_date.isoformat() if first_date else None,
        "last_date": last_date.isoformat() if last_date else None,
        "avg_per_day": round(total / span_days, 2),
        "top_type": top_type_row.msg_type if top_type_row else None,
    }


@router.get("/activity-by-month", summary="Monthly message volume")
async def stats_activity_by_month(
    request: Request,
    chat_id: ChatIdQuery,
    year: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Message count per calendar month. Defaults to the last 12 months when year is omitted."""
    await _check_group_access(chat_id, session, current_user, request)
    if year is not None:
        rows = (await session.execute(text("""
            SELECT TO_CHAR(DATE_TRUNC('month', date), 'YYYY-MM') AS month, COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id AND EXTRACT(YEAR FROM date) = :year
            GROUP BY month ORDER BY month
        """), {"chat_id": chat_id, "year": year})).fetchall()
    else:
        since = datetime.now(timezone.utc) - timedelta(days=365)
        rows = (await session.execute(text("""
            SELECT TO_CHAR(DATE_TRUNC('month', date), 'YYYY-MM') AS month, COUNT(id) AS cnt
            FROM stats_messages
            WHERE chat_id = :chat_id AND date >= :since
            GROUP BY month ORDER BY month
        """), {"chat_id": chat_id, "since": since})).fetchall()

    return [{"month": row.month, "count": int(row.cnt)} for row in rows]


@router.get("/ecdf", summary="Empirical CDF of messages per user")
async def stats_ecdf(
    request: Request,
    chat_id: ChatIdQuery,
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
            WHERE m.chat_id = :chat_id AND m.from_user IS NOT NULL
            GROUP BY m.from_user, un.username, un.display_name
            ORDER BY cnt DESC
            LIMIT :limit
        ),
        total AS (SELECT SUM(cnt) AS grand_total FROM per_user)
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
    chat_id: ChatIdQuery,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """History of chat title changes."""
    await _check_group_access(chat_id, session, current_user, request)
    rows = (await session.execute(text("""
        SELECT m.date, m.new_chat_title, m.from_user, un.username, un.display_name
        FROM stats_messages m
        LEFT JOIN LATERAL (
            SELECT username, display_name FROM stats_user_names
            WHERE user_id = m.from_user ORDER BY date DESC LIMIT 1
        ) un ON TRUE
        WHERE m.chat_id = :chat_id AND m.msg_type = 'new_chat_title'
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
    chat_id: ChatIdQuery,
    limit: int = Query(20, ge=1, le=100),
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top @mentions extracted from text messages."""
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
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Per-day message count and unique active users (DAU)."""
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
        GROUP BY day ORDER BY day
    """), params)).fetchall()

    return [{"date": str(row.day), "messages": int(row.messages), "dau": int(row.dau)} for row in rows]


@router.get("/member-events", summary="Group join/leave events over time")
async def stats_member_events(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Daily join/leave counts from user events."""
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
        GROUP BY day ORDER BY day
    """), params)).fetchall()

    return [{"date": str(row.day), "joined": int(row.joined), "left": int(row.left_count)} for row in rows]


@router.get("/avg-message-length", summary="Average message length by top users")
async def stats_avg_message_length(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Average text length per user (top N by message count)."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id, "limit": limit}
    date_filter = "AND m.date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            m.from_user AS user_id,
            COALESCE(un.display_name, u.first_name) AS display_name,
            COALESCE(un.username, u.username) AS username,
            COUNT(*) AS total,
            ROUND(AVG(LENGTH(COALESCE(m.text, m.caption, '')))) AS avg_len,
            MAX(LENGTH(COALESCE(m.text, m.caption, ''))) AS max_len
        FROM stats_messages m
        LEFT JOIN LATERAL (
            SELECT username, display_name FROM stats_user_names
            WHERE user_id = m.from_user ORDER BY date DESC LIMIT 1
        ) un ON TRUE
        LEFT JOIN users u ON u.id = m.from_user
        WHERE m.chat_id = :chat_id AND m.from_user IS NOT NULL
          AND COALESCE(m.text, m.caption) IS NOT NULL
          {date_filter}
        GROUP BY m.from_user, un.display_name, un.username, u.first_name, u.username
        ORDER BY total DESC
        LIMIT :limit
    """), params)).fetchall()

    return [
        {
            "user_id": row.user_id, "display_name": row.display_name, "username": row.username,
            "total": int(row.total), "avg_len": int(row.avg_len), "max_len": int(row.max_len),
        }
        for row in rows
    ]


@router.get("/response-time", summary="Median reply time between users")
async def stats_response_time(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Median and average response time, plus per-user breakdown."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id, "limit": limit}
    date_filter = "AND r.date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        WITH replies AS (
            SELECT
                r.from_user,
                EXTRACT(EPOCH FROM (r.date - o.date)) AS delay_sec
            FROM stats_messages r
            JOIN stats_messages o
                ON o.chat_id = r.chat_id AND o.message_id = r.reply_to_message
            WHERE r.chat_id = :chat_id
              AND r.reply_to_message IS NOT NULL
              AND r.from_user IS NOT NULL
              AND r.from_user != o.from_user
              AND EXTRACT(EPOCH FROM (r.date - o.date)) BETWEEN 1 AND 86400
              {date_filter}
        )
        SELECT
            rp.from_user AS user_id,
            COALESCE(un.display_name, u.first_name) AS display_name,
            COALESCE(un.username, u.username) AS username,
            COUNT(*) AS reply_count,
            ROUND(AVG(rp.delay_sec)) AS avg_sec,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rp.delay_sec) AS median_sec
        FROM replies rp
        LEFT JOIN LATERAL (
            SELECT username, display_name FROM stats_user_names
            WHERE user_id = rp.from_user ORDER BY date DESC LIMIT 1
        ) un ON TRUE
        LEFT JOIN users u ON u.id = rp.from_user
        GROUP BY rp.from_user, un.display_name, un.username, u.first_name, u.username
        ORDER BY reply_count DESC
        LIMIT :limit
    """), params)).fetchall()

    overall = (await session.execute(text(f"""
        SELECT
            ROUND(AVG(delay)) AS avg_sec,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay) AS median_sec,
            COUNT(*) AS total_replies
        FROM (
            SELECT EXTRACT(EPOCH FROM (r.date - o.date)) AS delay
            FROM stats_messages r
            JOIN stats_messages o
                ON o.chat_id = r.chat_id AND o.message_id = r.reply_to_message
            WHERE r.chat_id = :chat_id
              AND r.reply_to_message IS NOT NULL
              AND r.from_user IS NOT NULL
              AND r.from_user != COALESCE(o.from_user, 0)
              AND EXTRACT(EPOCH FROM (r.date - o.date)) BETWEEN 1 AND 86400
              {"AND r.date >= :since" if since else ""}
        ) sub
    """), {"chat_id": chat_id, **({"since": since} if since else {})})).fetchone()

    def fmt(sec: float | None) -> str:
        if sec is None:
            return "-"
        sec = int(sec)
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec // 60}m"
        return f"{sec // 3600}h {(sec % 3600) // 60}m"

    return {
        "overall_avg": fmt(overall.avg_sec) if overall else "-",
        "overall_median": fmt(overall.median_sec) if overall else "-",
        "total_replies": int(overall.total_replies) if overall else 0,
        "users": [
            {
                "user_id": row.user_id, "display_name": row.display_name, "username": row.username,
                "reply_count": int(row.reply_count), "avg": fmt(row.avg_sec), "median": fmt(row.median_sec),
            }
            for row in rows
        ],
    }


@router.get("/media-trend", summary="Media vs text ratio over months")
async def stats_media_trend(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Monthly breakdown of text vs media messages."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    params: dict = {"chat_id": chat_id}
    date_filter = "AND date >= :since" if since else ""
    if since:
        params["since"] = since

    rows = (await session.execute(text(f"""
        SELECT
            TO_CHAR(date AT TIME ZONE 'UTC', 'YYYY-MM') AS month,
            COUNT(*) FILTER (WHERE msg_type = 'text') AS text_count,
            COUNT(*) FILTER (WHERE msg_type != 'text') AS media_count,
            COUNT(*) AS total
        FROM stats_messages
        WHERE chat_id = :chat_id AND from_user IS NOT NULL {date_filter}
        GROUP BY month ORDER BY month
    """), params)).fetchall()

    return [
        {
            "month": row.month,
            "text": int(row.text_count),
            "media": int(row.media_count),
            "total": int(row.total),
            "media_pct": round(int(row.media_count) / int(row.total) * 100, 1) if int(row.total) > 0 else 0,
        }
        for row in rows
    ]


@router.get("/top-reactions", summary="Top reaction givers and most used emoji (admin only)")
async def stats_top_reactions(
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
) -> dict:
    """Top users by reactions given, and most-used emoji in the chat."""
    since = _since_param(days)
    date_filter = "AND r.date >= :since" if since else ""
    params: dict = {"chat_id": chat_id, "limit": limit}
    if since:
        params["since"] = since

    top_givers = (await session.execute(text(f"""
        SELECT
            r.user_id,
            COALESCE(un.display_name, u.first_name) AS display_name,
            COALESCE(un.username, u.username)        AS username,
            u.photo_url,
            COUNT(*) AS reaction_count
        FROM stats_reactions r
        LEFT JOIN users u ON u.id = r.user_id
        LEFT JOIN LATERAL (
            SELECT username, display_name FROM stats_user_names
            WHERE user_id = r.user_id ORDER BY date DESC LIMIT 1
        ) un ON true
        WHERE r.chat_id = :chat_id {date_filter}
        GROUP BY r.user_id, u.first_name, u.username, u.photo_url, un.username, un.display_name
        ORDER BY reaction_count DESC
        LIMIT :limit
    """), params)).fetchall()

    top_emoji = (await session.execute(text(f"""
        SELECT reaction_key, reaction_type, COUNT(*) AS cnt
        FROM stats_reactions r
        WHERE chat_id = :chat_id AND reaction_type IN ('emoji', 'custom_emoji') {date_filter}
        GROUP BY reaction_key, reaction_type
        ORDER BY cnt DESC
        LIMIT :limit
    """), params)).fetchall()

    return {
        "top_givers": [
            {
                "user_id": row.user_id, "display_name": row.display_name, "username": row.username,
                "has_photo": row.photo_url is not None, "reaction_count": row.reaction_count,
            }
            for row in top_givers
        ],
        "top_emoji": [
            {"reaction_key": row.reaction_key, "reaction_type": row.reaction_type, "count": row.cnt}
            for row in top_emoji
        ],
    }
