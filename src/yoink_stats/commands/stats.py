"""The /stats command with argparse-based subcommand dispatch."""
from __future__ import annotations

import argparse
import io
import logging
import sys
from typing import Any

from telegram import Update
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

_HELP = (
    "/stats [subcommand] [options]\n\n"
    "Subcommands:\n"
    "  counts   [-n N] [--type TYPE] [--start DATE] [--end DATE] [-q QUERY]\n"
    "  hours    [--user USER_ID] [--start DATE] [--end DATE] [-q QUERY]\n"
    "  days     [--user USER_ID] [--start DATE] [--end DATE] [-q QUERY]\n"
    "  week     [--user USER_ID] [-q QUERY]\n"
    "  history  [--days N] [--user USER_ID] [--start DATE] [--end DATE] [-q QUERY]\n"
    "  user     [USER_ID]\n"
    "  types    [--user USER_ID] [--start DATE] [--end DATE]\n"
    "  words    [-n N] [--start DATE] [--end DATE] [-q QUERY]\n"
    "  random   [--user USER_ID] [-q QUERY]\n"
    "  corr     USER_ID [TARGET_USER_ID]\n"
    "  delta    USER_ID [TARGET_USER_ID]\n"
    "  ecdf     [--start DATE] [--end DATE] [-q QUERY]\n"
    "  streak   USER_ID\n"
    "  rank     USER_ID [--start DATE] [--end DATE]\n"
    "  titles   [--start DATE] [--end DATE]\n"
    "  mention  [USER_ID] [--start DATE] [--end DATE] [-n LIMIT]\n"
    "\n"
    "DATE format: YYYY-MM-DD or ISO datetime"
)


class _NoExitParser(argparse.ArgumentParser):
    """ArgumentParser that raises ValueError instead of calling sys.exit."""

    def error(self, message: str) -> None:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise ValueError(message or "")


def _build_parser() -> _NoExitParser:
    parser = _NoExitParser(prog="/stats", add_help=False)
    sub = parser.add_subparsers(dest="subcommand")

    p_counts = sub.add_parser("counts", add_help=False)
    p_counts.add_argument("-n", "--limit", type=int, default=20)
    p_counts.add_argument("--type", dest="msg_type", default=None)
    p_counts.add_argument("--start", default=None)
    p_counts.add_argument("--end", default=None)
    p_counts.add_argument("-q", "--lquery", default=None)

    p_hours = sub.add_parser("hours", add_help=False)
    p_hours.add_argument("--user", dest="user_id", type=int, default=None)
    p_hours.add_argument("--start", default=None)
    p_hours.add_argument("--end", default=None)
    p_hours.add_argument("-q", "--lquery", default=None)

    p_days = sub.add_parser("days", add_help=False)
    p_days.add_argument("--user", dest="user_id", type=int, default=None)
    p_days.add_argument("--start", default=None)
    p_days.add_argument("--end", default=None)
    p_days.add_argument("-q", "--lquery", default=None)

    p_week = sub.add_parser("week", add_help=False)
    p_week.add_argument("--user", dest="user_id", type=int, default=None)
    p_week.add_argument("-q", "--lquery", default=None)

    p_history = sub.add_parser("history", add_help=False)
    p_history.add_argument("--days", type=int, default=30)
    p_history.add_argument("--user", dest="user_id", type=int, default=None)
    p_history.add_argument("--start", default=None)
    p_history.add_argument("--end", default=None)
    p_history.add_argument("-q", "--lquery", default=None)

    p_user = sub.add_parser("user", add_help=False)
    p_user.add_argument("target_user", type=int, nargs="?", default=None)

    p_types = sub.add_parser("types", add_help=False)
    p_types.add_argument("--user", dest="user_id", type=int, default=None)
    p_types.add_argument("--start", default=None)
    p_types.add_argument("--end", default=None)

    p_words = sub.add_parser("words", add_help=False)
    p_words.add_argument("-n", "--limit", type=int, default=20)
    p_words.add_argument("--start", default=None)
    p_words.add_argument("--end", default=None)
    p_words.add_argument("-q", "--lquery", default=None)

    p_random = sub.add_parser("random", add_help=False)
    p_random.add_argument("--user", dest="user_id", type=int, default=None)
    p_random.add_argument("-q", "--lquery", default=None)

    p_corr = sub.add_parser("corr", add_help=False)
    p_corr.add_argument("user_id", type=int)
    p_corr.add_argument("target_user_id", type=int, nargs="?", default=None)

    p_delta = sub.add_parser("delta", add_help=False)
    p_delta.add_argument("user_id", type=int)
    p_delta.add_argument("target_user_id", type=int, nargs="?", default=None)

    p_ecdf = sub.add_parser("ecdf", add_help=False)
    p_ecdf.add_argument("--start", default=None)
    p_ecdf.add_argument("--end", default=None)
    p_ecdf.add_argument("-q", "--lquery", default=None)

    p_streak = sub.add_parser("streak", add_help=False)
    p_streak.add_argument("user_id", type=int)

    p_rank = sub.add_parser("rank", add_help=False)
    p_rank.add_argument("user_id", type=int)
    p_rank.add_argument("--start", default=None)
    p_rank.add_argument("--end", default=None)

    p_titles = sub.add_parser("titles", add_help=False)
    p_titles.add_argument("--start", default=None)
    p_titles.add_argument("--end", default=None)

    p_mention = sub.add_parser("mention", add_help=False)
    p_mention.add_argument("user_id", type=int, nargs="?", default=None)
    p_mention.add_argument("--start", default=None)
    p_mention.add_argument("--end", default=None)
    p_mention.add_argument("-n", "--limit", type=int, default=20)

    return parser


async def _send_help(update: Update, extra: str = "") -> None:
    if not update.effective_user or not update.message:
        return
    text = (extra + "\n\n" if extra else "") + _HELP
    try:
        await update.effective_user.send_message(text)
    except Forbidden:
        await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return

    runner = context.bot_data.get("stats_runner")
    if runner is None:
        await update.message.reply_text("Stats service not available.")
        return

    args = list(context.args or [])
    if not args:
        await _send_help(update)
        return

    parser = _build_parser()
    try:
        ns = parser.parse_args(args)
    except ValueError as exc:
        await _send_help(update, str(exc))
        return

    if ns.subcommand is None:
        await _send_help(update)
        return

    chat_id = update.effective_chat.id
    effective_user_id = update.effective_user.id if update.effective_user else None

    try:
        text_result, image = await _dispatch(runner, ns, chat_id, effective_user_id)
    except Exception as exc:
        logger.exception("Stats runner error for subcommand %s", ns.subcommand)
        await update.message.reply_text(f"Error generating stats: {exc}")
        return

    if not text_result:
        text_result = "No data available for this group."

    if image is not None:
        await update.message.reply_photo(
            photo=image,
            caption=text_result[:1024] if len(text_result) > 1024 else text_result,
        )
    else:
        if len(text_result) > 4096:
            text_result = text_result[:4093] + "..."
        await update.message.reply_text(text_result)


async def _dispatch(
    runner: Any,
    ns: argparse.Namespace,
    chat_id: int,
    effective_user_id: int | None,
) -> tuple[str, bytes | None]:
    sub = ns.subcommand

    if sub == "counts":
        return await runner.counts(
            chat_id=chat_id,
            limit=ns.limit,
            msg_type=ns.msg_type,
            start=ns.start,
            end=ns.end,
            lquery=ns.lquery,
        )

    if sub == "hours":
        return await runner.hours(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
            lquery=ns.lquery,
        )

    if sub == "days":
        return await runner.days(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
            lquery=ns.lquery,
        )

    if sub == "week":
        return await runner.week(
            chat_id=chat_id,
            user_id=ns.user_id,
            lquery=ns.lquery,
        )

    if sub == "history":
        return await runner.history(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
            days=ns.days,
            lquery=ns.lquery,
        )

    if sub == "user":
        target = ns.target_user if ns.target_user is not None else effective_user_id
        if target is None:
            return "Please specify a user ID.", None
        return await runner.user_summary(chat_id=chat_id, user_id=target)

    if sub == "types":
        return await runner.types(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
        )

    if sub == "words":
        return await runner.words(
            chat_id=chat_id,
            limit=ns.limit,
            start=ns.start,
            end=ns.end,
            lquery=ns.lquery,
        )

    if sub == "random":
        return await runner.random_quote(
            chat_id=chat_id,
            user_id=ns.user_id,
            lquery=ns.lquery,
        )

    if sub == "corr":
        return await runner.corr(
            chat_id=chat_id,
            user_id=ns.user_id,
            target_user_id=ns.target_user_id,
        )

    if sub == "delta":
        return await runner.delta(
            chat_id=chat_id,
            user_id=ns.user_id,
            target_user_id=ns.target_user_id,
        )

    if sub == "ecdf":
        return await runner.ecdf(
            chat_id=chat_id,
            start=ns.start,
            end=ns.end,
            lquery=ns.lquery,
        )

    if sub == "streak":
        return await runner.streak(
            chat_id=chat_id,
            user_id=ns.user_id,
        )

    if sub == "rank":
        return await runner.rank(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
        )

    if sub == "titles":
        return await runner.title_history(
            chat_id=chat_id,
            start=ns.start,
            end=ns.end,
        )

    if sub == "mention":
        return await runner.mention(
            chat_id=chat_id,
            user_id=ns.user_id,
            start=ns.start,
            end=ns.end,
            limit=ns.limit,
        )

    return f"Unknown subcommand: {sub}", None


def register(app: Application) -> None:
    app.add_handler(CommandHandler("stats", cmd_stats), group=1)
