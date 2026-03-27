"""Event analytics: chat title history."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics._base import code as _code, parse_dt as _parse_dt


class EventsMixin:
    _sf: async_sessionmaker

    async def title_history(
        self,
        chat_id: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id", "msg_type = 'new_chat_title'"]
        params: dict[str, Any] = {"chat_id": chat_id}
        if dt_start:
            conditions.append("date >= :start")
            params["start"] = dt_start
        if dt_end:
            conditions.append("date <= :end")
            params["end"] = dt_end

        where = " AND ".join(conditions)
        sql = text(f"""
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
            WHERE {where}
            ORDER BY m.date
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No title changes recorded for this group.", None

        lines = [f"Chat title history ({len(rows)} change{'s' if len(rows) != 1 else ''}):"]
        lines.append(f"{'Date':<12} | {'Title':<30} | Changed by")
        lines.append("-" * 60)
        for row in rows:
            date_str = row.date.strftime("%Y-%m-%d") if row.date else "?"
            title = (row.new_chat_title or "")[:30]
            if row.username:
                changer = f"@{row.username}"
            elif row.display_name:
                changer = row.display_name
            else:
                changer = str(row.from_user) if row.from_user else "?"
            lines.append(f"{date_str:<12} | {title:<30} | {changer}")

        return _code("\n".join(lines)), None

