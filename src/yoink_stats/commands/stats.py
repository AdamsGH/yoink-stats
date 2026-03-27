"""The /stats command with argparse-based subcommand dispatch."""
from __future__ import annotations

import argparse
import logging
from typing import Any

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Help text (expandable blockquotes, HTML, per-language)
# ---------------------------------------------------------------------------

_GUIDE = {
    "en": (
        "Run <b>/stats</b> inside a group — all subcommands query the chat where messages are collected.\n\n"
        "<b>Date ranges</b> — most subcommands accept <code>--start</code> and <code>--end</code> "
        "(format: <code>YYYY-MM-DD</code>).\n"
        "Example: <code>/stats counts --start 2024-01-01 --end 2024-06-30</code>\n\n"
        "<b>Full-text search</b> — add <code>-q WORD</code> to filter by text.\n"
        "Example: <code>/stats words -q music</code>\n\n"
        "<b>Per-user scope</b> — add <code>--user USER_ID</code> to scope to one person.\n"
        "Example: <code>/stats hours --user 123456789</code>"
    ),
    "ru": (
        "Используй <b>/stats</b> в группе — все подкоманды работают там, где собираются сообщения.\n\n"
        "<b>Диапазон дат</b> — большинство подкоманд принимают <code>--start</code> и <code>--end</code> "
        "(формат: <code>YYYY-MM-DD</code>).\n"
        "Пример: <code>/stats counts --start 2024-01-01 --end 2024-06-30</code>\n\n"
        "<b>Поиск по тексту</b> — добавь <code>-q СЛОВО</code> для фильтрации.\n"
        "Пример: <code>/stats words -q музыка</code>\n\n"
        "<b>По пользователю</b> — добавь <code>--user USER_ID</code> для одного человека.\n"
        "Пример: <code>/stats hours --user 123456789</code>"
    ),
}

_COMMANDS = {
    "en": (
        "<code>counts</code>   [-n N] [--type TYPE] — top senders\n"
        "<code>hours</code>    [--user ID] — activity by hour\n"
        "<code>days</code>     [--user ID] — activity by day of week\n"
        "<code>week</code>     [--user ID] — last-7-days heatmap\n"
        "<code>history</code>  [--days N] [--user ID] — daily message chart\n"
        "<code>user</code>     [USER_ID] — personal summary\n"
        "<code>types</code>    [--user ID] — message type breakdown\n"
        "<code>words</code>    [-n N] [-q QUERY] — top words\n"
        "<code>random</code>   [--user ID] [-q QUERY] — random quote\n"
        "<code>rank</code>     USER_ID — ranking in the group\n"
        "<code>streak</code>   USER_ID — activity streak\n"
        "<code>ecdf</code>     — message distribution curve\n"
        "<code>corr</code>     USER_ID — activity correlation with chat\n"
        "<code>delta</code>    USER_ID — median response time\n"
        "<code>titles</code>   — chat title history\n"
        "<code>mention</code>  [USER_ID] — @mention stats\n\n"
        "All date-aware subcommands accept <code>--start</code>/<code>--end</code> (YYYY-MM-DD)."
    ),
    "ru": (
        "<code>counts</code>   [-n N] [--type TYPE] — топ отправителей\n"
        "<code>hours</code>    [--user ID] — активность по часам\n"
        "<code>days</code>     [--user ID] — активность по дням недели\n"
        "<code>week</code>     [--user ID] — тепловая карта за 7 дней\n"
        "<code>history</code>  [--days N] [--user ID] — история по дням\n"
        "<code>user</code>     [USER_ID] — сводка по пользователю\n"
        "<code>types</code>    [--user ID] — типы сообщений\n"
        "<code>words</code>    [-n N] [-q ЗАПРОС] — топ слов\n"
        "<code>random</code>   [--user ID] [-q ЗАПРОС] — случайная цитата\n"
        "<code>rank</code>     USER_ID — место в рейтинге\n"
        "<code>streak</code>   USER_ID — серия активности\n"
        "<code>ecdf</code>     — кривая распределения сообщений\n"
        "<code>corr</code>     USER_ID — корреляция активности с чатом\n"
        "<code>delta</code>    USER_ID — медианное время ответа\n"
        "<code>titles</code>   — история названий чата\n"
        "<code>mention</code>  [USER_ID] — статистика @упоминаний\n\n"
        "Все подкоманды с датами принимают <code>--start</code>/<code>--end</code> (YYYY-MM-DD)."
    ),
}

_LABELS = {
    "en": {"guide": "How to use", "commands": "Commands", "unavailable": "Stats service not available.", "no_data": "No data."},
    "ru": {"guide": "Как пользоваться", "commands": "Команды", "unavailable": "Сервис статистики недоступен.", "no_data": "Нет данных."},
}


def _build_help(lang: str = "en", error: str = "") -> str:
    lab = _LABELS.get(lang, _LABELS["en"])
    g = _GUIDE.get(lang, _GUIDE["en"])
    c = _COMMANDS.get(lang, _COMMANDS["en"])
    parts: list[str] = []
    if error:
        parts.append(f"<i>{error}</i>\n")
    parts.append(f"<blockquote expandable><b>{lab['guide']}</b>\n{g}</blockquote>")
    parts.append(f"<blockquote expandable><b>{lab['commands']}</b>\n{c}</blockquote>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

class _NoExitParser(argparse.ArgumentParser):
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_lang(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Resolve user language from bot_data user_repo."""
    try:
        user_repo = context.bot_data.get("user_repo")
        if user_repo:
            user = await user_repo.get_or_create(user_id)
            return getattr(user, "language", "en") or "en"
    except Exception:
        pass
    return "en"


async def _send_help(
    update: Update,
    lang: str = "en",
    error: str = "",
    in_group: bool = False,
) -> None:
    """Send help. In groups replies in-chat; in private sends directly."""
    if not update.effective_user or not update.message:
        return
    text = _build_help(lang=lang, error=error)
    if in_group:
        # In a group, reply in the group so it's contextual
        await update.message.reply_html(text)
    else:
        # In private, just reply
        await update.message.reply_html(text)


# ---------------------------------------------------------------------------
# Main command handler
# ---------------------------------------------------------------------------

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    lang = await _get_lang(context, update.effective_user.id)
    lab = _LABELS.get(lang, _LABELS["en"])
    is_private = update.effective_chat.type == ChatType.PRIVATE

    runner = context.bot_data.get("stats_runner")
    if runner is None:
        await update.message.reply_html(lab["unavailable"])
        return

    args = list(context.args or [])

    # No args: send help. In private — directly here. In group — reply in chat.
    if not args:
        await _send_help(update, lang=lang, in_group=not is_private)
        return

    # In private with args but no group context: can't run group queries
    if is_private:
        # user subcommand works anywhere (uses calling user's id)
        # everything else needs a group chat_id
        if args[0] != "user":
            await update.message.reply_html(_build_help(lang=lang))
            return

    parser = _build_parser()
    try:
        ns = parser.parse_args(args)
    except ValueError as exc:
        await _send_help(update, lang=lang, error=str(exc), in_group=not is_private)
        return

    if ns.subcommand is None:
        await _send_help(update, lang=lang, in_group=not is_private)
        return

    chat_id = update.effective_chat.id
    effective_user_id = update.effective_user.id

    # For /stats user in private, use the calling user as chat_id doesn't matter —
    # we look up by from_user across all chats if no group context is available.
    # Pass user's private chat_id as a sentinel; user_summary filters by from_user only.
    if is_private and ns.subcommand == "user":
        target = ns.target_user if ns.target_user is not None else effective_user_id
        # user_summary needs a real group chat_id — we can't run it without one in private
        # so we list the groups the user appears in and pick the first, or explain
        try:
            from sqlalchemy import select, text as sa_text
            from yoink_stats.storage.models import ChatMessage
            sf = context.bot_data.get("session_factory")
            if sf:
                async with sf() as session:
                    row = (await session.execute(
                        select(ChatMessage.chat_id)
                        .where(ChatMessage.from_user == target)
                        .where(ChatMessage.chat_id < 0)
                        .limit(1)
                    )).fetchone()
                if row:
                    chat_id = row.chat_id
                else:
                    await update.message.reply_html(lab["no_data"])
                    return
        except Exception as exc:
            logger.warning("Could not resolve group for user %d: %s", target, exc)
            await update.message.reply_html(lab["no_data"])
            return

    try:
        text_result, image = await _dispatch(runner, ns, chat_id, effective_user_id)
    except Exception as exc:
        logger.exception("Stats runner error for subcommand %s", ns.subcommand)
        await update.message.reply_html(f"Error: <code>{exc}</code>")
        return

    if not text_result:
        text_result = lab["no_data"]

    if image is not None:
        await update.message.reply_photo(
            photo=image,
            caption=text_result[:1024] if len(text_result) > 1024 else text_result,
            parse_mode=ParseMode.HTML,
        )
    else:
        for chunk in _split(text_result, 4096):
            await update.message.reply_html(chunk)


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def _dispatch(
    runner: Any,
    ns: argparse.Namespace,
    chat_id: int,
    effective_user_id: int | None,
) -> tuple[str, bytes | None]:
    sub = ns.subcommand

    if sub == "counts":
        return await runner.counts(
            chat_id=chat_id, limit=ns.limit, msg_type=ns.msg_type,
            start=ns.start, end=ns.end, lquery=ns.lquery,
        )
    if sub == "hours":
        return await runner.hours(
            chat_id=chat_id, user_id=ns.user_id,
            start=ns.start, end=ns.end, lquery=ns.lquery,
        )
    if sub == "days":
        return await runner.days(
            chat_id=chat_id, user_id=ns.user_id,
            start=ns.start, end=ns.end, lquery=ns.lquery,
        )
    if sub == "week":
        return await runner.week(chat_id=chat_id, user_id=ns.user_id, lquery=ns.lquery)
    if sub == "history":
        return await runner.history(
            chat_id=chat_id, user_id=ns.user_id,
            start=ns.start, end=ns.end, days=ns.days, lquery=ns.lquery,
        )
    if sub == "user":
        target = ns.target_user if ns.target_user is not None else effective_user_id
        if target is None:
            return "Please specify a user ID.", None
        return await runner.user_summary(chat_id=chat_id, user_id=target)
    if sub == "types":
        return await runner.types(
            chat_id=chat_id, user_id=ns.user_id, start=ns.start, end=ns.end,
        )
    if sub == "words":
        return await runner.words(
            chat_id=chat_id, limit=ns.limit,
            start=ns.start, end=ns.end, lquery=ns.lquery,
        )
    if sub == "random":
        return await runner.random_quote(
            chat_id=chat_id, user_id=ns.user_id, lquery=ns.lquery,
        )
    if sub == "corr":
        return await runner.corr(
            chat_id=chat_id, user_id=ns.user_id, target_user_id=ns.target_user_id,
        )
    if sub == "delta":
        return await runner.delta(
            chat_id=chat_id, user_id=ns.user_id, target_user_id=ns.target_user_id,
        )
    if sub == "ecdf":
        return await runner.ecdf(chat_id=chat_id, start=ns.start, end=ns.end, lquery=ns.lquery)
    if sub == "streak":
        return await runner.streak(chat_id=chat_id, user_id=ns.user_id)
    if sub == "rank":
        return await runner.rank(
            chat_id=chat_id, user_id=ns.user_id, start=ns.start, end=ns.end,
        )
    if sub == "titles":
        return await runner.title_history(chat_id=chat_id, start=ns.start, end=ns.end)
    if sub == "mention":
        return await runner.mention(
            chat_id=chat_id, user_id=ns.user_id,
            start=ns.start, end=ns.end, limit=ns.limit,
        )

    return f"Unknown subcommand: {sub}", None


def register(app: Application) -> None:
    app.add_handler(CommandHandler("stats", cmd_stats), group=1)
