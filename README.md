# yoink-stats

Analytics plugin for [yoink-core](https://github.com/AdamsGH/yoink-core). Passively logs all group messages and provides statistics via bot commands and a web dashboard.

Included in yoink-core as a git submodule at `plugins/yoink-stats`.

## Bot command

`/stats` - available for moderator+ in group chats. Shows a statistics menu.

## API endpoints

Mounted at `/api/v1/stats/`. Auth: JWT Bearer token with group membership check.

| Method | Path | Description |
|---|---|---|
| GET | /groups | List groups with message counts |
| GET | /overview | Message totals for a group |
| GET | /top-users | Top message senders |
| GET | /activity-by-hour | Messages by hour of day |
| GET | /activity-by-day | Messages by day of week |
| GET | /activity-by-week | Weekly heatmap data |
| GET | /activity-by-month | Monthly activity |
| GET | /message-types | Type breakdown (text, photo, video, etc) |
| GET | /history | Message volume over time |
| GET | /words | Top words (full-text search) |
| GET | /user-stats | Per-user detailed stats |
| GET | /ecdf | Empirical CDF of message lengths |
| GET | /title-history | Group title changes |
| GET | /mention-stats | Mention statistics |
| POST | /import | Import chat history from JSON export |

All endpoints accept `chat_id` and `days` (7/30/90) query parameters.

## Frontend

Interactive dashboard at `/stats` in the Telegram WebApp:

- Group listing with message counts
- Group dashboard with charts (recharts): activity by hour/day, message types, top users, history
- Per-user detail page (`/stats/:chatId/user/:userId`) - total messages, average per day, top type, first/last message dates
- Clickable top-users chart navigating to user detail
- Period toggle (7d / 30d / 90d)
- JSON/CSV export buttons
- Catppuccin color theme (Latte / Frappe / Macchiato / Mocha)
- Skeleton loading states
- i18n (en / ru)

## Package structure

```
src/yoink_stats/
  plugin.py            # entry point (StatsPlugin)
  api/router.py        # FastAPI routes (raw SQL queries)
  collector/           # message logging handlers
  i18n/locales/        # translations (en.yml, ru.yml)
frontend/
  manifest.tsx         # route registration for core SPA
  src/
    pages/
      stats/
        index.tsx      # group listing
        group.tsx      # group dashboard with charts
        user.tsx       # per-user stats
      import/
        index.tsx      # chat history import
    types/
      index.ts         # TypeScript type definitions
```
