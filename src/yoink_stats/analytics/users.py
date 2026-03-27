"""User analytics: counts, user summary, ecdf, streak, rank."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics._base import bar as _bar, code as _code, parse_dt as _parse_dt, resolve_identity


class UsersMixin:
    _sf: async_sessionmaker

    async def counts(
        self,
        chat_id: int,
        limit: int = 20,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        msg_type: str | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["m.chat_id = :chat_id", "m.from_user IS NOT NULL"]
        params: dict[str, Any] = {"chat_id": chat_id, "limit": limit}
        if dt_start:
            conditions.append("m.date >= :start")
            params["start"] = dt_start
        if dt_end:
            conditions.append("m.date <= :end")
            params["end"] = dt_end
        if msg_type:
            conditions.append("m.msg_type = :msg_type")
            params["msg_type"] = msg_type
        if lquery:
            conditions.append("m.text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
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
            WHERE {where}
            GROUP BY m.from_user, un.username, un.display_name
            ORDER BY cnt DESC
            LIMIT :limit
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        type_label = f" ({msg_type})" if msg_type else ""
        header = f"Top {limit} senders{type_label}:\n"
        header += f"{'#':<4} {'User':<24} {'Messages':>8}\n"
        header += "-" * 40 + "\n"

        lines = []
        for i, row in enumerate(rows, 1):
            if row.username:
                name = f"@{row.username}"
            elif row.display_name:
                name = row.display_name
            else:
                name = str(row.from_user)
            name = name[:24]
            lines.append(f"{i:<4} {name:<24} {row.cnt:>8}")

        return _code(header + "\n".join(lines)), None

    async def user_summary(
        self,
        chat_id: int,
        user_id: int,
    ) -> tuple[str, None]:
        sql = text("""
            SELECT
                COUNT(id) AS total,
                MIN(date) AS first_msg,
                MAX(date) AS last_msg,
                msg_type,
                COUNT(id) OVER () AS total_all
            FROM stats_messages
            WHERE chat_id = :chat_id AND from_user = :user_id
            GROUP BY msg_type
            ORDER BY COUNT(id) DESC
        """)

        async with self._sf() as session:
            result = await session.execute(sql, {"chat_id": chat_id, "user_id": user_id})
            rows = result.fetchall()

            name_result = await session.execute(text("""
                SELECT username, display_name
                FROM stats_user_names
                WHERE user_id = :user_id
                ORDER BY date DESC
                LIMIT 1
            """), {"user_id": user_id})
            name_row = name_result.fetchone()

        if not rows:
            return f"No messages found for user {user_id} in this group.", None

        total = sum(row.total for row in rows)
        first_msg: datetime = rows[0].first_msg
        last_msg: datetime = rows[0].last_msg
        for row in rows:
            if row.first_msg < first_msg:
                first_msg = row.first_msg
            if row.last_msg > last_msg:
                last_msg = row.last_msg

        span_days = max((last_msg - first_msg).days, 1)
        avg_per_day = total / span_days
        top_type = rows[0].msg_type

        if name_row and name_row.username:
            identity = f"@{name_row.username}"
        elif name_row and name_row.display_name:
            identity = name_row.display_name
        else:
            identity = str(user_id)

        lines = [
            f"User: {identity} (id={user_id})",
            f"Total messages: {total}",
            f"Avg per day: {avg_per_day:.1f}",
            f"First message: {first_msg.strftime('%Y-%m-%d %H:%M')} UTC",
            f"Last message:  {last_msg.strftime('%Y-%m-%d %H:%M')} UTC",
            f"Top type: {top_type}",
            "",
            "Message types:",
        ]
        for row in rows:
            pct = row.total / total * 100
            lines.append(f"  {row.msg_type:<20} {row.total:>6} ({pct:.1f}%)")

        return _code("\n".join(lines)), None

    async def ecdf(
        self,
        chat_id: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id", "from_user IS NOT NULL"]
        params: dict[str, Any] = {"chat_id": chat_id}
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
                WHERE {where}
                GROUP BY m.from_user, un.username, un.display_name
                ORDER BY cnt DESC
                LIMIT 20
            ),
            total AS (
                SELECT SUM(cnt) AS grand_total FROM per_user
            )
            SELECT
                p.from_user,
                p.cnt,
                p.username,
                p.display_name,
                t.grand_total,
                SUM(p.cnt) OVER (ORDER BY p.cnt DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumul
            FROM per_user p, total t
            ORDER BY p.cnt DESC
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        grand_total = int(rows[0].grand_total) if rows[0].grand_total else 1
        n_users = len(rows)

        lines = [f"Message count distribution ({n_users} users):"]
        lines.append(f" {'Rank':>4}  | {'User':<20} | {'Count':>7}  | Cumul%")
        lines.append("-" * 50)
        for i, row in enumerate(rows, 1):
            if row.username:
                name = f"@{row.username}"
            elif row.display_name:
                name = row.display_name
            else:
                name = str(row.from_user)
            name = name[:20]
            cumul_pct = int(row.cumul) / grand_total * 100
            lines.append(f" {i:>4}  | {name:<20} | {int(row.cnt):>7}  | {cumul_pct:>6.1f}%")

        return _code("\n".join(lines)), None

    async def streak(
        self,
        chat_id: int,
        user_id: int,
    ) -> tuple[str, None]:
        sql = text("""
            WITH daily AS (
                SELECT DISTINCT DATE(date) AS day
                FROM stats_messages
                WHERE chat_id = :chat_id AND from_user = :user_id
            ),
            groups AS (
                SELECT day,
                       day - (ROW_NUMBER() OVER (ORDER BY day) * INTERVAL '1 day') AS grp
                FROM daily
            ),
            streaks AS (
                SELECT COUNT(*) AS len, MIN(day) AS start, MAX(day) AS finish
                FROM groups
                GROUP BY grp
            ),
            current_streak AS (
                SELECT len, start, finish
                FROM streaks
                ORDER BY finish DESC
                LIMIT 1
            ),
            max_streak AS (
                SELECT len AS max_len, start AS max_start, finish AS max_finish
                FROM streaks
                WHERE len = (SELECT MAX(len) FROM streaks)
                ORDER BY finish DESC
                LIMIT 1
            )
            SELECT
                c.len AS cur_len,
                c.start AS cur_start,
                c.finish AS cur_finish,
                m.max_len,
                m.max_start,
                m.max_finish
            FROM current_streak c, max_streak m
        """)

        name_sql = text("""
            SELECT username, display_name
            FROM stats_user_names
            WHERE user_id = :user_id
            ORDER BY date DESC
            LIMIT 1
        """)

        async with self._sf() as session:
            result = await session.execute(sql, {"chat_id": chat_id, "user_id": user_id})
            row = result.fetchone()
            name_result = await session.execute(name_sql, {"user_id": user_id})
            name_row = name_result.fetchone()

        if row is None:
            return f"No messages found for user {user_id} in this group.", None

        if name_row and name_row.username:
            identity = f"@{name_row.username}"
        elif name_row and name_row.display_name:
            identity = name_row.display_name
        else:
            identity = str(user_id)

        cur_len = int(row.cur_len)
        cur_start = str(row.cur_start)[:10]
        cur_finish = str(row.cur_finish)[:10]
        max_len = int(row.max_len)
        max_start = str(row.max_start)[:10]
        max_finish = str(row.max_finish)[:10]

        lines = [
            f"Streak stats for {identity}:",
            f"Current streak: {cur_len} day{'s' if cur_len != 1 else ''} ({cur_start} - {cur_finish})",
            f"Longest streak: {max_len} day{'s' if max_len != 1 else ''} ({max_start} - {max_finish})",
        ]
        return "\n".join(lines), None

    async def rank(
        self,
        chat_id: int,
        user_id: int,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id", "from_user IS NOT NULL"]
        params: dict[str, Any] = {"chat_id": chat_id, "user_id": user_id}
        if dt_start:
            conditions.append("date >= :start")
            params["start"] = dt_start
        if dt_end:
            conditions.append("date <= :end")
            params["end"] = dt_end

        where = " AND ".join(conditions)
        sql = text(f"""
            WITH per_user AS (
                SELECT
                    from_user,
                    COUNT(id) AS cnt
                FROM stats_messages
                WHERE {where}
                GROUP BY from_user
            ),
            ranked AS (
                SELECT
                    from_user,
                    cnt,
                    RANK() OVER (ORDER BY cnt DESC) AS rnk,
                    COUNT(*) OVER () AS total_users,
                    SUM(cnt) OVER () AS grand_total
                FROM per_user
            )
            SELECT rnk, cnt, total_users, grand_total
            FROM ranked
            WHERE from_user = :user_id
        """)

        name_sql = text("""
            SELECT username, display_name
            FROM stats_user_names
            WHERE user_id = :user_id
            ORDER BY date DESC
            LIMIT 1
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            row = result.fetchone()
            name_result = await session.execute(name_sql, {"user_id": user_id})
            name_row = name_result.fetchone()

        if row is None:
            return f"No messages found for user {user_id} in this group.", None

        if name_row and name_row.username:
            identity = f"@{name_row.username}"
        elif name_row and name_row.display_name:
            identity = name_row.display_name
        else:
            identity = str(user_id)

        rnk = int(row.rnk)
        cnt = int(row.cnt)
        total_users = int(row.total_users)
        grand_total = int(row.grand_total)
        pct = cnt / grand_total * 100 if grand_total else 0.0

        lines = [
            f"{identity} rank: #{rnk} of {total_users} users",
            f"Messages: {cnt:,} ({pct:.1f}% of total {grand_total:,})",
        ]
        return "\n".join(lines), None

