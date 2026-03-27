"""Shared utilities for stats analytics modules."""
from __future__ import annotations

from datetime import datetime, timezone


_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_STOPWORDS = frozenset([
    "the","a","an","in","on","at","to","of","is","it","and","or",
    "but","for","with","i","you","he","she","we","they","this",
    "that","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","my","your",
    "his","her","its","our","their","not","no","so","if","as",
    "by","up","from","what","who","how","when","where","which",
])


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def bar(count: int, max_count: int, width: int = 20) -> str:
    if max_count == 0:
        return ""
    filled = round(count / max_count * width)
    return "█" * filled + "░" * (width - filled)


def code(text: str) -> str:
    """Wrap in HTML <code> block to preserve monospace alignment in Telegram."""
    return f"<code>{text}</code>"


def resolve_identity(name_row: object | None, user_id: int) -> str:
    if name_row and getattr(name_row, "username", None):
        return f"@{name_row.username}"  # type: ignore[union-attr]
    if name_row and getattr(name_row, "display_name", None):
        return name_row.display_name  # type: ignore[union-attr]
    return str(user_id)


NAME_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT username, display_name
        FROM stats_user_names
        WHERE user_id = {col}
        ORDER BY date DESC
        LIMIT 1
    ) un ON TRUE
"""
