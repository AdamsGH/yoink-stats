"""Standalone entry: runs yoink-core + stats plugin."""
from __future__ import annotations

import logging

from telegram import Update

from yoink.core.config import CoreSettings
from yoink.app import build_app
from yoink_stats.plugin import StatsPlugin

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)


def main() -> None:
    config = CoreSettings()
    app = build_app(config=config, plugins=[StatsPlugin()])
    app.run_polling(
        allowed_updates=["message", "edited_message", "channel_post"],
        drop_pending_updates=True,
        bootstrap_retries=-1,
        poll_interval=0.5,
        timeout=10,
    )
