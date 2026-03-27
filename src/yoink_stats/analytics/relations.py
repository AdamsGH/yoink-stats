"""Relation analytics: activity correlation, median response time."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics._base import parse_dt as _parse_dt


class RelationsMixin:
    _sf: async_sessionmaker

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

