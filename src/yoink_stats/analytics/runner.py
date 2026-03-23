"""StatsRunner: executes analytical queries and returns text summaries."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_STOPWORDS = frozenset(
    ["the", "a", "an", "in", "on", "at", "to", "of", "is", "it",
     "and", "or", "but", "for", "with", "i", "you", "he", "she",
     "we", "they", "this", "that", "are", "was", "were", "be",
     "been", "have", "has", "had", "do", "does", "did", "will",
     "would", "could", "should", "my", "your", "his", "her", "its",
     "our", "their", "not", "no", "so", "if", "as", "by", "up",
     "from", "what", "who", "how", "when", "where", "which"]
)


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _bar(count: int, max_count: int, width: int = 20) -> str:
    if max_count == 0:
        return ""
    filled = round(count / max_count * width)
    return "█" * filled + "░" * (width - filled)


class StatsRunner:
    """Runs statistical queries. Each method returns (text, None)."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

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

        return header + "\n".join(lines), None

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

        return "\n".join(lines), None

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

        return "\n".join(lines), None

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
        return "\n".join(lines), None

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

        return "\n".join(lines), None

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

        return "\n".join(lines), None

    async def types(
        self,
        chat_id: int,
        user_id: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
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

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT msg_type, COUNT(id) AS cnt
            FROM stats_messages
            WHERE {where}
            GROUP BY msg_type
            ORDER BY cnt DESC
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No data available for this group.", None

        total = sum(row.cnt for row in rows)
        max_cnt = rows[0].cnt

        lines = [f"Message types (total={total}):"]
        lines.append(f"{'Type':<20} {'Count':>6} {'%':>6} | Bar")
        lines.append("-" * 50)
        for row in rows:
            pct = row.cnt / total * 100
            bar = _bar(row.cnt, max_cnt, 12)
            lines.append(f"{row.msg_type:<20} {row.cnt:>6} {pct:>5.1f}% | {bar}")

        return "\n".join(lines), None

    async def words(
        self,
        chat_id: int,
        limit: int = 20,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        conditions = ["chat_id = :chat_id", "(text IS NOT NULL OR caption IS NOT NULL)"]
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
            WITH messages AS (
                SELECT COALESCE(text, '') || ' ' || COALESCE(caption, '') AS body
                FROM stats_messages
                WHERE {where}
            ),
            words AS (
                SELECT lower(regexp_replace(w, '[^[:alpha:]]', '', 'g')) AS word
                FROM messages,
                     regexp_split_to_table(body, '\\s+') AS w
                WHERE length(regexp_replace(w, '[^[:alpha:]]', '', 'g')) >= 3
            )
            SELECT word, COUNT(*) AS cnt
            FROM words
            WHERE word NOT IN (
                'the','a','an','in','on','at','to','of','is','it','and','or',
                'but','for','with','i','you','he','she','we','they','this',
                'that','are','was','were','be','been','have','has','had',
                'do','does','did','will','would','could','should','my','your',
                'his','her','its','our','their','not','no','so','if','as',
                'by','up','from','what','who','how','when','where','which'
            )
              AND word <> ''
            GROUP BY word
            ORDER BY cnt DESC
            LIMIT :limit
        """)
        params["limit"] = limit

        async with self._sf() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        if not rows:
            return "No word data available for this group.", None

        max_cnt = rows[0].cnt
        lines = [f"Top {limit} words:"]
        lines.append(f"{'Word':<20} {'Count':>6} | Bar")
        lines.append("-" * 40)
        for row in rows:
            bar = _bar(row.cnt, max_cnt, 12)
            lines.append(f"{row.word:<20} {row.cnt:>6} | {bar}")

        return "\n".join(lines), None

    async def random_quote(
        self,
        chat_id: int,
        user_id: int | None = None,
        lquery: str | None = None,
    ) -> tuple[str, None]:
        conditions = [
            "chat_id = :chat_id",
            "msg_type = 'text'",
            "text IS NOT NULL",
            "LENGTH(text) > 5",
        ]
        params: dict[str, Any] = {"chat_id": chat_id}
        if user_id is not None:
            conditions.append("from_user = :user_id")
            params["user_id"] = user_id
        if lquery:
            conditions.append("text_search @@ plainto_tsquery('simple', :lquery)")
            params["lquery"] = lquery

        where = " AND ".join(conditions)
        sql = text(f"""
            SELECT m.text, m.date, m.from_user, un.username, un.display_name
            FROM stats_messages m
            LEFT JOIN LATERAL (
                SELECT username, display_name
                FROM stats_user_names
                WHERE user_id = m.from_user
                ORDER BY date DESC
                LIMIT 1
            ) un ON TRUE
            WHERE {where}
            ORDER BY random()
            LIMIT 1
        """)

        async with self._sf() as session:
            result = await session.execute(sql, params)
            row = result.fetchone()

        if row is None:
            return "No text messages found.", None

        if row.username:
            author = f"@{row.username}"
        elif row.display_name:
            author = row.display_name
        else:
            author = str(row.from_user)

        date_str = row.date.strftime("%Y-%m-%d") if row.date else "?"
        quote_text = row.text or ""
        return f'"{quote_text}"\n\n- {author}, {date_str}', None

    async def corr(
        self,
        chat_id: int,
        user_id: int,
        target_user_id: int | None = None,
    ) -> tuple[str, None]:
        if target_user_id is None:
            sql = text("""
                WITH daily AS (
                    SELECT
                        DATE(date AT TIME ZONE 'UTC') AS day,
                        SUM(CASE WHEN from_user = :user_id THEN 1 ELSE 0 END) AS u1,
                        SUM(CASE WHEN from_user != :user_id THEN 1 ELSE 0 END) AS u2
                    FROM stats_messages
                    WHERE chat_id = :chat_id
                      AND from_user IS NOT NULL
                    GROUP BY day
                )
                SELECT CORR(u1, u2) AS correlation
                FROM daily
            """)
            params: dict[str, Any] = {"chat_id": chat_id, "user_id": user_id}
            label = f"user {user_id} vs all others"
        else:
            sql = text("""
                WITH daily AS (
                    SELECT
                        DATE(date AT TIME ZONE 'UTC') AS day,
                        SUM(CASE WHEN from_user = :user_id THEN 1 ELSE 0 END) AS u1,
                        SUM(CASE WHEN from_user = :target_id THEN 1 ELSE 0 END) AS u2
                    FROM stats_messages
                    WHERE chat_id = :chat_id
                      AND from_user IN (:user_id, :target_id)
                    GROUP BY day
                )
                SELECT CORR(u1, u2) AS correlation
                FROM daily
            """)
            params = {"chat_id": chat_id, "user_id": user_id, "target_id": target_user_id}
            label = f"user {user_id} vs user {target_user_id}"

        async with self._sf() as session:
            result = await session.execute(sql, params)
            row = result.fetchone()

        if row is None or row.correlation is None:
            return "Not enough data to compute correlation.", None

        corr_val = float(row.correlation)
        if corr_val > 0.7:
            interpretation = "strong positive correlation (both active on same days)"
        elif corr_val > 0.3:
            interpretation = "moderate positive correlation"
        elif corr_val > -0.3:
            interpretation = "weak or no correlation"
        elif corr_val > -0.7:
            interpretation = "moderate negative correlation"
        else:
            interpretation = "strong negative correlation (active on different days)"

        return (
            f"Pearson correlation ({label}):\n"
            f"r = {corr_val:.4f}\n"
            f"{interpretation}"
        ), None

    async def delta(
        self,
        chat_id: int,
        user_id: int,
        target_user_id: int | None = None,
    ) -> tuple[str, None]:
        if target_user_id is None:
            sql = text("""
                WITH replies AS (
                    SELECT
                        m.date AS reply_time,
                        prev.date AS orig_time,
                        EXTRACT(EPOCH FROM (m.date - prev.date)) / 60.0 AS gap_minutes
                    FROM stats_messages m
                    JOIN stats_messages prev
                        ON prev.chat_id = m.chat_id
                        AND prev.message_id = m.reply_to_message
                    WHERE m.chat_id = :chat_id
                      AND m.from_user = :user_id
                      AND m.reply_to_message IS NOT NULL
                      AND prev.from_user != :user_id
                      AND EXTRACT(EPOCH FROM (m.date - prev.date)) BETWEEN 1 AND 86400
                )
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap_minutes) AS median_minutes,
                    COUNT(*) AS reply_count
                FROM replies
            """)
            params: dict[str, Any] = {"chat_id": chat_id, "user_id": user_id}
            label = f"user {user_id} replying to others"
        else:
            sql = text("""
                WITH replies AS (
                    SELECT
                        m.date AS reply_time,
                        prev.date AS orig_time,
                        EXTRACT(EPOCH FROM (m.date - prev.date)) / 60.0 AS gap_minutes
                    FROM stats_messages m
                    JOIN stats_messages prev
                        ON prev.chat_id = m.chat_id
                        AND prev.message_id = m.reply_to_message
                    WHERE m.chat_id = :chat_id
                      AND m.from_user = :user_id
                      AND m.reply_to_message IS NOT NULL
                      AND prev.from_user = :target_id
                      AND EXTRACT(EPOCH FROM (m.date - prev.date)) BETWEEN 1 AND 86400
                )
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap_minutes) AS median_minutes,
                    COUNT(*) AS reply_count
                FROM replies
            """)
            params = {"chat_id": chat_id, "user_id": user_id, "target_id": target_user_id}
            label = f"user {user_id} replying to user {target_user_id}"

        async with self._sf() as session:
            result = await session.execute(sql, params)
            row = result.fetchone()

        if row is None or row.median_minutes is None or row.reply_count == 0:
            return "Not enough reply data to compute response time.", None

        median = float(row.median_minutes)
        count = int(row.reply_count)

        if median < 1:
            time_str = f"{median * 60:.0f} seconds"
        elif median < 60:
            time_str = f"{median:.1f} minutes"
        else:
            time_str = f"{median / 60:.1f} hours"

        return (
            f"Median response time ({label}):\n"
            f"{time_str} (based on {count} replies)"
        ), None

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

        return "\n".join(lines), None

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

        return "\n".join(lines), None

    async def mention(
        self,
        chat_id: int,
        user_id: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit: int = 20,
    ) -> tuple[str, None]:
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)

        base_conditions = ["chat_id = :chat_id"]
        params: dict[str, Any] = {"chat_id": chat_id, "limit": limit}
        if dt_start:
            base_conditions.append("date >= :start")
            params["start"] = dt_start
        if dt_end:
            base_conditions.append("date <= :end")
            params["end"] = dt_end

        if user_id is None:
            where = " AND ".join(base_conditions)
            sql = text(f"""
                SELECT lower(m[1]) AS mention, COUNT(*) AS cnt
                FROM stats_messages,
                     regexp_matches(COALESCE(text, ''), '@([a-zA-Z0-9_]{{4,}})', 'g') AS m
                WHERE {where}
                GROUP BY mention
                ORDER BY cnt DESC
                LIMIT :limit
            """)

            async with self._sf() as session:
                result = await session.execute(sql, params)
                rows = result.fetchall()

            if not rows:
                return "No @mentions found in this group.", None

            lines = [f"Top {limit} @mentions in chat:"]
            lines.append(f"{'Mention':<25} | Count")
            lines.append("-" * 35)
            for row in rows:
                lines.append(f"@{row.mention:<24} | {int(row.cnt):>6}")
            return "\n".join(lines), None

        # user_id provided: who mentions this user, and who this user mentions
        name_sql = text("""
            SELECT username, display_name
            FROM stats_user_names
            WHERE user_id = :user_id
            ORDER BY date DESC
            LIMIT 1
        """)

        async with self._sf() as session:
            name_result = await session.execute(name_sql, {"user_id": user_id})
            name_row = name_result.fetchone()

        if name_row and name_row.username:
            identity = f"@{name_row.username}"
            target_username = name_row.username
        elif name_row and name_row.display_name:
            identity = name_row.display_name
            target_username = None
        else:
            identity = str(user_id)
            target_username = None

        by_user_conditions = base_conditions + ["from_user = :user_id"]
        params["user_id"] = user_id
        by_user_where = " AND ".join(by_user_conditions)

        by_user_sql = text(f"""
            SELECT lower(m[1]) AS mention, COUNT(*) AS cnt
            FROM stats_messages,
                 regexp_matches(COALESCE(text, ''), '@([a-zA-Z0-9_]{{4,}})', 'g') AS m
            WHERE {by_user_where}
            GROUP BY mention
            ORDER BY cnt DESC
            LIMIT :limit
        """)

        lines = [f"Mention stats for {identity}:"]

        async with self._sf() as session:
            by_user_result = await session.execute(by_user_sql, params)
            by_user_rows = by_user_result.fetchall()

            if target_username:
                of_user_conditions = base_conditions + [
                    "text ILIKE :pattern",
                    "from_user != :user_id",
                ]
                of_user_params = {**params, "pattern": f"%@{target_username}%"}
                of_user_where = " AND ".join(of_user_conditions)
                of_user_sql = text(f"""
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
                    WHERE {of_user_where}
                    GROUP BY m.from_user, un.username, un.display_name
                    ORDER BY cnt DESC
                    LIMIT :limit
                """)
                of_user_result = await session.execute(of_user_sql, of_user_params)
                of_user_rows = of_user_result.fetchall()
            else:
                of_user_rows = []

        lines.append("")
        lines.append(f"Mentioned by {identity}:")
        if by_user_rows:
            lines.append(f"  {'Mention':<22} | Count")
            lines.append("  " + "-" * 32)
            for row in by_user_rows:
                lines.append(f"  @{row.mention:<21} | {int(row.cnt):>5}")
        else:
            lines.append("  (no mentions found)")

        if target_username:
            lines.append("")
            lines.append(f"Who mentions {identity}:")
            if of_user_rows:
                lines.append(f"  {'User':<22} | Count")
                lines.append("  " + "-" * 32)
                for row in of_user_rows:
                    if row.username:
                        name = f"@{row.username}"
                    elif row.display_name:
                        name = row.display_name
                    else:
                        name = str(row.from_user)
                    lines.append(f"  {name:<22} | {int(row.cnt):>5}")
            else:
                lines.append("  (no mentions found)")

        return "\n".join(lines), None
