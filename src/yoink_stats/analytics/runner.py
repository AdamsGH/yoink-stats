"""StatsRunner: facade that composes all analytics mixins."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_stats.analytics.activity import ActivityMixin
from yoink_stats.analytics.content import ContentMixin
from yoink_stats.analytics.events import EventsMixin
from yoink_stats.analytics.relations import RelationsMixin
from yoink_stats.analytics.users import UsersMixin


class StatsRunner(ActivityMixin, UsersMixin, ContentMixin, RelationsMixin, EventsMixin):
    """Runs statistical queries and returns (text, image|None) tuples.

    Methods are split by domain:
      activity  - hours, days, week, history
      users     - counts, user_summary, ecdf, streak, rank
      content   - types, words, random_quote, mention
      relations - corr, delta
      events    - title_history
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory
