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
        from yoink_stats.storage.models import ChatMessage, GroupMember, Reaction, UserEvent, UserNameHistory
        return [ChatMessage, GroupMember, Reaction, UserEvent, UserNameHistory]

    def get_features(self) -> list:
        from yoink.core.plugin import FeatureSpec
        return [
            FeatureSpec(
                plugin="stats",
                feature="stats",
                label="Chat Statistics",
                description="Access to /stats command and analytics dashboard",
                default_min_role="user",
            ),
        ]

    def get_commands(self) -> list:
        from yoink.core.plugin import CommandSpec
        return [
            CommandSpec(
                command="stats",
                description="Chat statistics",
                min_role="user",
                scope="groups",
                descriptions={"ru": "Статистика чата"},
            ),
            CommandSpec(
                command="stats",
                description="Chat statistics",
                min_role="user",
                scope="private",
                descriptions={"ru": "Статистика чата"},
            ),
        ]

    def get_help_section(self, role: str, lang: str, granted_features: set[str] | None = None) -> str:
        _titles = {"en": "Chat Stats", "ru": "Статистика чата"}
        _bodies = {
            "en": (
                "/stats — run in a group to query its stats\n"
                "/stats user — your personal summary (works in private)\n"
                "/stats counts · hours · days · week · history · words · random\n"
                "/stats rank · streak · ecdf · corr · delta · titles · mention\n"
                "\n<i>Add <code>-q QUERY</code> for full-text search, "
                "<code>--start</code>/<code>--end</code> for date ranges.</i>"
            ),
            "ru": (
                "/stats — запускай в группе для просмотра её статистики\n"
                "/stats user — личная сводка (работает в личке)\n"
                "/stats counts · hours · days · week · history · words · random\n"
                "/stats rank · streak · ecdf · corr · delta · titles · mention\n"
                "\n<i>Добавь <code>-q ЗАПРОС</code> для поиска по тексту, "
                "<code>--start</code>/<code>--end</code> для диапазона дат.</i>"
            ),
        }
        title = _titles.get(lang, _titles["en"])
        body = _bodies.get(lang, _bodies["en"])
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
        from yoink_stats.storage.repos import MessageRepo, ReactionRepo, UserEventRepo, UserNameRepo

        sf = ctx.session_factory
        bd = ctx.bot_data

        bd["stats_config"] = self._config
        bd["stats_message_repo"] = MessageRepo(sf)
        bd["stats_event_repo"] = UserEventRepo(sf)
        bd["stats_name_repo"] = UserNameRepo(sf)
        bd["stats_reaction_repo"] = ReactionRepo(sf)
        bd["stats_runner"] = StatsRunner(sf)
