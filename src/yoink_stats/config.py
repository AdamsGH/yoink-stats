"""Stats plugin configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class StatsConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Comma-separated group IDs to collect stats for (empty = all enabled groups)
    stats_group_ids: list[int] = []

    # How many messages to keep per group (0 = unlimited)
    stats_max_messages: int = 0

    # Username refresh interval in seconds
    stats_refresh_interval: int = 3600

    # Enable chart generation
    stats_charts_enabled: bool = True
