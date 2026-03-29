# yoink-stats

Analytics plugin for [yoink-core](https://github.com/AdamsGH/yoink-core). Passively logs all group messages and provides statistics via bot commands and a React web dashboard.

Included in yoink-core as a git submodule at `plugins/yoink-stats`.

## Bot command

`/stats` - available in group chats and private chat. Shows a statistics menu with subcommands.

```
/stats counts · hours · days · week · history · words · random
/stats rank · streak · ecdf · corr · delta · titles · mention
/stats user        - personal summary (works in private)
/stats -q QUERY    - full-text search filter
/stats --start DATE --end DATE
```

## RBAC

`FeatureSpec(stats:stats, default_min_role=user)` - accessible to all users by default, no explicit grant required.

## API endpoints

Mounted at `/api/v1/stats/`. Auth: JWT Bearer token.

All endpoints accept `chat_id` and optional `days` (7/30/90) query parameters.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /groups | user | Groups with message counts |
| GET | /overview | user | Message totals for a group |
| GET | /top-users | user | Top message senders |
| GET | /activity-by-hour | user | Messages by hour of day |
| GET | /activity-by-day | user | Messages by day of week |
| GET | /activity-by-week | user | Weekly heatmap |
| GET | /activity-by-month | user | Monthly activity |
| GET | /message-types | user | Type breakdown (text, photo, video, etc) |
| GET | /history | user | Message volume over time |
| GET | /words | user | Top words |
| GET | /user-stats | user | Per-user detailed stats |
| GET | /ecdf | user | Empirical CDF of message lengths |
| GET | /title-history | user | Group title changes |
| GET | /mention-stats | user | Mention statistics |
| GET | /daily-activity | user | DAU + message count per day |
| GET | /member-events | user | Join/leave events per day |
| POST | /import | admin | Import chat history from JSON export |

## Frontend

Interactive dashboard at `/stats` in the Telegram WebApp:

- Stats index page: Card with Item list showing groups and message counts
- Group dashboard: compact header, activity by hour/day, message types, top users, history, DAU, member events
- **PeriodToggle** component (7d / 30d / 90d) - applies to all charts on the group page
- **RankedList** component - used for top words and top mentions with ranked rows
- Per-user detail page (`/stats/:chatId/user/:userId`)
- JSON/CSV export
- Catppuccin color theme (Latte / Frappe / Macchiato / Mocha)
- Skeleton loading states
- i18n (en / ru)

## Configuration

| Variable | Default | Description |
|---|---|---|
| `stats_refresh_interval` | `3600` | Username refresh job interval, seconds |

## Package structure

```
src/yoink_stats/
  plugin.py              # entry point (StatsPlugin)
  config.py              # StatsConfig
  api/router.py          # FastAPI routes
  analytics/
    _base.py             # StatsBase mixin
    activity.py          # ActivityMixin - hourly/daily/weekly/monthly
    users.py             # UsersMixin - top users, user detail, DAU
    content.py           # ContentMixin - message types, words, ecdf
    relations.py         # RelationsMixin - correlations, mentions
    events.py            # EventsMixin - join/leave events, title history
    runner.py            # StatsRunner facade
  collector/             # message logging handlers
  commands/stats.py      # /stats command handler
  storage/               # SQLAlchemy models and repos
  i18n/locales/          # translations (en.yml, ru.yml)
frontend/
  manifest.tsx           # route registration
  src/pages/
    stats/
      index.tsx          # group listing
      group.tsx          # group dashboard with charts
      user.tsx           # per-user stats
    import/index.tsx     # chat history import
```
