"""Import command - owner sends result.json as document to the bot in PM."""
from __future__ import annotations

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from yoink.core.db.models import UserRole

logger = logging.getLogger(__name__)


async def _handle_import_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Owner only
    config = context.bot_data.get("config")
    if not config or user.id != config.owner_id:
        from yoink.core.db.models import User
        repo = context.bot_data.get("dl_user_repo") or context.bot_data.get("user_repo")
        if repo:
            u = await repo.get_or_create(user.id)
            if u.role not in (UserRole.owner, UserRole.admin):
                return
        else:
            return

    doc = msg.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".json"):
        return

    # Parse caption for chat_id: /import -100123456789
    chat_id: int | None = None
    caption = (msg.caption or "").strip()
    if caption:
        parts = caption.split()
        for part in parts:
            try:
                chat_id = int(part)
                break
            except ValueError:
                pass

    if chat_id is None:
        await msg.reply_text(
            "Send result.json with caption containing the chat ID.\n"
            "Example caption: <code>-1001234567890</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await msg.reply_text("⏳ Downloading file…")

    try:
        tg_file = await doc.get_file()
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        await tg_file.download_to_drive(tmp.name)
        tmp.close()
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to download file: {e}")
        return

    await status_msg.edit_text("⏳ Starting import…")

    async def _run() -> None:
        try:
            from yoink_stats.importer.json_dump import import_json
            from yoink.core.config import CoreSettings
            cfg = CoreSettings()

            last_pct = [-1]

            def _progress(done: int, total: int) -> None:
                if total == 0:
                    return
                pct = int(done / total * 100)
                if pct - last_pct[0] >= 10:
                    last_pct[0] = pct
                    context.application.create_task(
                        status_msg.edit_text(f"⏳ Importing… {pct}% ({done:,} / {total:,})")
                    )

            result = await import_json(
                json_path=tmp.name,
                db_url=cfg.database_url,
                chat_id=chat_id,
                progress_cb=_progress,
            )
            await status_msg.edit_text(
                f"✅ Import complete\n"
                f"Inserted: {result['inserted']:,}\n"
                f"Skipped: {result['skipped']:,}\n"
                f"Events: {result['events']:,}"
            )
        except Exception as e:
            logger.exception("Import failed for chat_id=%s", chat_id)
            await status_msg.edit_text(f"❌ Import failed: {e}")
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    context.application.create_task(_run())


def register(app: Application) -> None:
    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("json") & filters.ChatType.PRIVATE,
            _handle_import_doc,
        )
    )
