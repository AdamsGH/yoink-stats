"""Content analytics: message types, words, random quote, mentions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics._base import bar as _bar, code as _code, parse_dt as _parse_dt


class ContentMixin:
    _sf: async_sessionmaker

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

        return _code("\n".join(lines)), None

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

        return _code("\n".join(lines)), None

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
            return _code("\n".join(lines)), None

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

        return _code("\n".join(lines)), None

