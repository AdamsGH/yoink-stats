"""Activity analytics: hours, days, week heatmap, message history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics._base import bar as _bar, code as _code, parse_dt as _parse_dt, _DAYS


class ActivityMixin:
    _sf: async_sessionmaker

    async def hours(
        self,
        chat_id: int,
        user_id: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id"]
        params: dict[str, Any] = {"chat_id": chat_id}
        if user_id is not None:
            conditions.append("from_user = :user_id")
            params["user_id"] = user_id
        if dt_start:
            conditions.append("date >= :start")
            params["start"] = dt_start
        if dt_end:
            conditions.append("date <= :end")
            params["end"] = dt_end
        if lquery:
            conditions.append("text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT EXTRACT(HOUR FROM date)::int AS hour, COUNT(id) AS cnt
            FROM stats_messages
            WHERE {where}
            GROUP BY hour
            ORDER BY hour
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        data = {row.hour: row.cnt for row in rows}
        max_cnt = max(data.values())

        lines = ["Hour | Count  | Bar"]
        lines.append("-" * 36)
        for h in range(24):
            cnt = data.get(h, 0)
            bar = _bar(cnt, max_cnt, 16)
            lines.append(f"{h:02d}:00 | {cnt:>6} | {bar}")

        return _code("\n".join(lines)), None

    async def days(
        self,
        chat_id: int,
        user_id: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id"]
        params: dict[str, Any] = {"chat_id": chat_id}
        if user_id is not None:
            conditions.append("from_user = :user_id")
            params["user_id"] = user_id
        if dt_start:
            conditions.append("date >= :start")
            params["start"] = dt_start
        if dt_end:
            conditions.append("date <= :end")
            params["end"] = dt_end
        if lquery:
            conditions.append("text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT
                ((EXTRACT(DOW FROM date)::int + 6) % 7) AS dow,
                COUNT(id) AS cnt
            FROM stats_messages
            WHERE {where}
            GROUP BY dow
            ORDER BY dow
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        data = {row.dow: row.cnt for row in rows}
        max_cnt = max(data.values())

        lines = ["Day       | Count  | Bar"]
        lines.append("-" * 38)
        for d in range(7):
            cnt = data.get(d, 0)
            bar = _bar(cnt, max_cnt, 16)
            lines.append(f"{_DAYS[d]:<9} | {cnt:>6} | {bar}")

        return _code("\n".join(lines)), None

    async def week(
        self,
        chat_id: int,
        user_id: int | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        conditions = ["chat_id = :chat_id"]
        params: dict[str, Any] = {"chat_id": chat_id}
        if user_id is not None:
            conditions.append("from_user = :user_id")
            params["user_id"] = user_id
        if lquery:
            conditions.append("text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT
                ((EXTRACT(DOW FROM date)::int + 6) % 7) AS dow,
                EXTRACT(HOUR FROM date)::int AS hour,
                COUNT(id) AS cnt
            FROM stats_messages
            WHERE {where}
            GROUP BY dow, hour
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        grid: dict[tuple[int, int], int] = {}
        for row in rows:
            grid[(int(row.dow), int(row.hour))] = int(row.cnt)

        max_cnt = max(grid.values()) if grid else 1
        chars = " ░▒▓█"

        header = "     " + "".join(f"{h:02d}" for h in range(0, 24, 2))
        lines = [header]
        for d in range(7):
            cells = []
            for h in range(24):
                cnt = grid.get((d, h), 0)
                idx = min(int(cnt / max_cnt * (len(chars) - 1)), len(chars) - 1) if max_cnt else 0
                cells.append(chars[idx] if h % 2 == 0 else "")
            lines.append(f"{_DAYS[d]:<4} {''.join(cells)}")

        lines.append(f"(max={max_cnt} msgs in a single day+hour slot)")
        return _code("\n".join(lines)), None

    async def history(
        self,
        chat_id: int,
        user_id: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        days: int = 30,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_end = _parse_dt(end) or datetime.now(timezone.utc)
        dt_start = _parse_dt(start) or (dt_end - timedelta(days=days))

        conditions = ["chat_id = :chat_id", "date >= :start", "date <= :end"]
        params: dict[str, Any] = {"chat_id": chat_id, "start": dt_start, "end": dt_end}
        if user_id is not None:
            conditions.append("from_user = :user_id")
            params["user_id"] = user_id
        if lquery:
            conditions.append("text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT DATE(date AT TIME ZONE 'UTC') AS day, COUNT(id) AS cnt
            FROM stats_messages
            WHERE {where}
            GROUP BY day
            ORDER BY day
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        data = {str(row.day): int(row.cnt) for row in rows}
        max_cnt = max(data.values())
        total = sum(data.values())

        lines = [f"Daily messages ({dt_start.date()} to {dt_end.date()}):"]
        lines.append(f"Total: {total} | Peak: {max_cnt}")
        lines.append("")

        for day_str, cnt in sorted(data.items()):
            bar = _bar(cnt, max_cnt, 20)
            lines.append(f"{day_str} | {cnt:>5} | {bar}")

        return _code("\n".join(lines)), None

