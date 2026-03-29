"""Analytics endpoints - message stats, activity charts, word/mention frequency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import cast, func, select, text, distinct, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from yoink.core.api.deps import get_db
from yoink.core.auth.rbac import require_role, role_gte
from yoink.core.db.models import Group, User, UserGroupPolicy, UserRole
from yoink.core.db.query import date_params, load_sql
from yoink_stats.api.routers._deps import (
    ChatIdQuery, DaysQuery, _check_group_access, _since_param,
)

router = APIRouter(tags=["stats"])

_Q = Path(__file__).parent.parent.parent / "queries"

_SQL_TOP_USERS          = load_sql(_Q, "top_users")
_SQL_ACTIVITY_BY_DAY    = load_sql(_Q, "activity_by_day")
_SQL_ACTIVITY_BY_WEEK   = load_sql(_Q, "activity_by_week")
_SQL_ACTIVITY_BY_MONTH  = load_sql(_Q, "activity_by_month")
_SQL_HISTORY            = load_sql(_Q, "history")
_SQL_WORDS              = load_sql(_Q, "words")
_SQL_USER_SUMMARY       = load_sql(_Q, "user_stats_summary")
_SQL_USER_REACTIONS     = load_sql(_Q, "user_stats_reactions")
_SQL_USER_TOP_TYPE      = load_sql(_Q, "user_stats_top_type")
_SQL_USER_NAME          = load_sql(_Q, "user_latest_name")
_SQL_ECDF               = load_sql(_Q, "ecdf")
_SQL_TITLE_HISTORY      = load_sql(_Q, "title_history")
_SQL_MENTION_STATS      = load_sql(_Q, "mention_stats")
_SQL_DAILY_ACTIVITY     = load_sql(_Q, "daily_activity")
_SQL_MEMBER_EVENTS      = load_sql(_Q, "member_events")
_SQL_AVG_MSG_LEN        = load_sql(_Q, "avg_message_length")
_SQL_RESP_TIME_USERS    = load_sql(_Q, "response_time_users")
_SQL_RESP_TIME_OVERALL  = load_sql(_Q, "response_time_overall")
_SQL_MEDIA_TREND        = load_sql(_Q, "media_trend")
_SQL_TOP_GIVERS         = load_sql(_Q, "top_reaction_givers")
_SQL_TOP_EMOJI          = load_sql(_Q, "top_emoji")


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
            from yoink_stats.storage.models import ChatMessage as CM  # noqa: PLC0415
            visible_ids = select(distinct(CM.chat_id)).where(CM.from_user == current_user.id)
            q = q.where(Group.id.in_(visible_ids))

    rows = (await session.execute(q)).fetchall()
    return [{"chat_id": row.id, "title": row.title, "message_count": row.message_count} for row in rows]


@router.get("/overview", summary="Chat statistics overview")
async def stats_overview(
    request: Request,
    chat_id: ChatIdQuery,
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> dict:
    """Summary stats: total messages, unique users, date range."""
    await _check_group_access(chat_id, session, current_user, request)
    from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415

    since = _since_param(days)
    q = select(
        func.count(ChatMessage.id).label("total"),
        func.count(distinct(ChatMessage.from_user)).label("unique_users"),
        func.min(ChatMessage.date).label("first_date"),
        func.max(ChatMessage.date).label("last_date"),
    ).where(ChatMessage.chat_id == chat_id)
    if since:
        q = q.where(ChatMessage.date >= since)
    row = (await session.execute(q)).fetchone()
    if not row:
        return {"total": 0, "unique_users": 0, "first_date": None, "last_date": None, "avg_per_day": 0.0}

    total = row.total or 0
    first_date: datetime | None = row.first_date
    last_date: datetime | None = row.last_date
    if first_date and last_date:
        span = max((last_date - first_date).days, 1)
        avg = round(total / span, 2)
    else:
        avg = 0.0
    return {
        "total": total,
        "unique_users": row.unique_users or 0,
        "first_date": first_date.isoformat() if first_date else None,
        "last_date": last_date.isoformat() if last_date else None,
        "avg_per_day": avg,
    }


@router.get("/top-users", summary="Top users by message count")
async def stats_top_users(
    request: Request,
    chat_id: ChatIdQuery,
    limit: int = Query(10, ge=1, le=100),
    days: DaysQuery = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.user)),
) -> list[dict]:
    """Top N message senders with username, display name and avatar flag."""
    await _check_group_access(chat_id, session, current_user, request)
    since = _since_param(days)
    rows = (await session.execute(
        text(_SQL_TOP_USERS),
        date_params(since, chat_id=chat_id, limit=limit),
    )).fetchall()
    return [
        {
            "user_id": row.from_user, "username": row.username,
            "display_name": row.display_name, "count": int(row.cnt),
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
    rows = (await session.execute(
        text(_SQL_ACTIVITY_BY_DAY),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_ACTIVITY_BY_WEEK),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    since = _since_param(days)
    rows = (await session.execute(
        text(_SQL_HISTORY),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_WORDS),
        date_params(since, chat_id=chat_id, limit=limit),
    )).fetchall()
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

    summary = (await session.execute(
        text(_SQL_USER_SUMMARY), {"chat_id": chat_id, "user_id": user_id},
    )).fetchone()

    reaction_row = (await session.execute(
        text(_SQL_USER_REACTIONS), {"chat_id": chat_id, "user_id": user_id},
    )).fetchone()
    reaction_count = int(reaction_row.reaction_count) if reaction_row else 0

    if not summary or not summary.total:
        return {
            "user_id": user_id, "username": None, "display_name": None,
            "total": 0, "reaction_count": reaction_count,
            "first_date": None, "last_date": None, "avg_per_day": 0.0, "top_type": None,
        }

    top_type_row = (await session.execute(
        text(_SQL_USER_TOP_TYPE), {"chat_id": chat_id, "user_id": user_id},
    )).fetchone()

    name_row = (await session.execute(
        text(_SQL_USER_NAME), {"user_id": user_id},
    )).fetchone()

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
        since = datetime(year, 1, 1, tzinfo=timezone.utc)
        until = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        from yoink_stats.storage.models import ChatMessage  # noqa: PLC0415
        q = (
            select(
                func.to_char(func.date_trunc("month", ChatMessage.date), "YYYY-MM").label("month"),
                func.count(ChatMessage.id).label("cnt"),
            )
            .where(ChatMessage.chat_id == chat_id)
            .where(ChatMessage.date >= since)
            .where(ChatMessage.date < until)
            .group_by(text("month"))
            .order_by(text("month"))
        )
        rows = (await session.execute(q)).fetchall()
    else:
        since = datetime.now(timezone.utc) - timedelta(days=365)
        rows = (await session.execute(
            text(_SQL_ACTIVITY_BY_MONTH),
            date_params(since, chat_id=chat_id),
        )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_ECDF), {"chat_id": chat_id, "limit": limit},
    )).fetchall()
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
    rows = (await session.execute(text(_SQL_TITLE_HISTORY), {"chat_id": chat_id})).fetchall()
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
    rows = (await session.execute(
        text(_SQL_MENTION_STATS),
        date_params(since, chat_id=chat_id, limit=limit),
    )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_DAILY_ACTIVITY),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_MEMBER_EVENTS),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    rows = (await session.execute(
        text(_SQL_AVG_MSG_LEN),
        date_params(since, chat_id=chat_id, limit=limit),
    )).fetchall()
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
    params = date_params(since, chat_id=chat_id, limit=limit)

    rows = (await session.execute(text(_SQL_RESP_TIME_USERS), params)).fetchall()
    overall = (await session.execute(
        text(_SQL_RESP_TIME_OVERALL), date_params(since, chat_id=chat_id),
    )).fetchone()

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
    rows = (await session.execute(
        text(_SQL_MEDIA_TREND),
        date_params(since, chat_id=chat_id),
    )).fetchall()
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
    params = date_params(since, chat_id=chat_id, limit=limit)

    top_givers = (await session.execute(text(_SQL_TOP_GIVERS), params)).fetchall()
    top_emoji = (await session.execute(text(_SQL_TOP_EMOJI), params)).fetchall()

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
