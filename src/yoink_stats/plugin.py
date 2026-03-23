"""StatsPlugin - implements YoinkPlugin protocol."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from yoink.core.plugin import JobSpec, PluginContext, WebManifest, WebPage, SidebarEntry
from yoink_stats.config import StatsConfig


class StatsPlugin:
    name = "stats"
    version = "0.1.0"

    def __init__(self) -> None:
        self._config = StatsConfig()

    def get_config_class(self) -> type[StatsConfig]:
        return StatsConfig

    def get_models(self) -> list:
        from yoink_stats.storage.models import ChatMessage, UserEvent, UserNameHistory
        return [ChatMessage, UserEvent, UserNameHistory]

    def get_commands(self) -> list:
        from yoink.core.plugin import CommandSpec
        return [
            CommandSpec(
                command="stats",
                description="Chat statistics",
                min_role="user",
                scope="groups",
            ),
        ]

    def get_help_section(self, role: str, lang: str) -> str:
        from yoink.core.i18n import t

        _ROLE_RANK = {"user": 0, "moderator": 1, "admin": 2, "owner": 3}
        rank = _ROLE_RANK.get(role, 0)

        # Stats is a moderator+ feature; users don't see it
        if rank < _ROLE_RANK.get("moderator", 1):
            return ""

        title = "Chat Stats"
        body = (
            "/stats counts   - top active users\n"
            "/stats hours    - activity by hour\n"
            "/stats days     - activity by day of week\n"
            "/stats week     - last 7 days chart\n"
            "/stats history  - message history\n"
            "/stats user [ID] - personal summary\n"
            "/stats words    - top words\n"
            "/stats random   - random quote\n"
            "/stats rank ID  - user rank\n"
            "/stats streak ID - activity streak\n"
            "\n<i>All subcommands support <code>-q QUERY</code> for full-text search.</i>"
        )
        return f"<blockquote expandable><b>{title}</b>\n{body}</blockquote>"

    def get_handlers(self) -> list:
        from yoink_stats.commands import get_handler_specs
        return get_handler_specs()

    def get_routes(self) -> APIRouter | None:
        from yoink_stats.api.router import router
        return router

    def get_locale_dir(self) -> Path | None:
        locale_dir = Path(__file__).parent / "i18n" / "locales"
        return locale_dir if locale_dir.exists() else None

    def get_web_manifest(self) -> WebManifest:
        return WebManifest(pages=[
            WebPage(
                path="/stats",
                sidebar=SidebarEntry(
                    label="Stats", icon="BarChart2", path="/stats",
                    section="main", min_role="user",
                ),
            ),
            WebPage(path="/stats/group/:id"),
        ])

    def get_jobs(self) -> list[JobSpec]:
        from yoink_stats.collector.user_tracker import refresh_usernames
        return [
            JobSpec(
                callback=refresh_usernames,
                interval=self._config.stats_refresh_interval,
                first=60,
                name="stats_refresh_usernames",
            ),
        ]

    async def setup(self, ctx: PluginContext) -> None:
        """Populate bot_data with stats-specific services.

        Namespaced keys (never overwrite core keys):
          "stats_message_repo"  - MessageRepo
          "stats_event_repo"    - UserEventRepo
          "stats_name_repo"     - UserNameRepo
          "stats_runner"        - StatsRunner
          "stats_config"        - StatsConfig
        """
        from yoink_stats.analytics.runner import StatsRunner
        from yoink_stats.storage.repos import MessageRepo, UserEventRepo, UserNameRepo

        sf = ctx.session_factory
        bd = ctx.bot_data

        bd["stats_config"] = self._config
        bd["stats_message_repo"] = MessageRepo(sf)
        bd["stats_event_repo"] = UserEventRepo(sf)
        bd["stats_name_repo"] = UserNameRepo(sf)
        bd["stats_runner"] = StatsRunner(sf)
