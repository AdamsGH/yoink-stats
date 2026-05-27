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
| GET | /avg-message-length | user | Average message length by user |
| GET | /response-time | user | Response time distribution |
| GET | /media-trend | user | Media type trend over time |
| GET | /top-reactions | admin | Top reaction givers and top emoji |
| GET | /members | user | Group members with activity stats |
| POST | /members/sync | admin | Sync members via getChatMembers |
| GET | /chat-admins | user | Chat admins for access check |
| POST | /import | admin | Import chat history from JSON export |
| POST | /import/by-path | admin | Import from server-side file path |
| GET | /import/{job_id} | admin | Poll import job status |

## Frontend

Interactive dashboard at `/stats` in the Telegram WebApp:

- Stats index page: single Card with Item list; each row shows group name, message count, period toggle
- Group dashboard (`/stats/:chatId`): compact header with KPI grid (total messages, active users, avg/day), PeriodToggle (7d/30d/90d), activity charts, top users, history chart, DAU, member events
- Per-user page (`/stats/:chatId/user/:userId`): individual activity breakdown
- **Members tab**: visible to admins and chat admins; shows activity per member with active/inactive badge; sync button for full member list
- **Reactions**: top reaction givers and top emoji cards (admin only)
- **RankedList** component: compact ranked rows for top words, mentions, reactions
- **PeriodToggle** component: 7d / 30d / 90d buttons, shared across all charts on a page
- **UserStatsDrawer**: reusable drawer for per-user stats, used in top-users list and Members tab
- JSON/CSV export
- Catppuccin color theme (Latte / Frappe / Macchiato / Mocha)
- Skeleton loading states with opacity-fade during refetch (no skeleton flash)
- i18n (en / ru)

## Configuration

| Variable | Default | Description |
|---|---|---|
| `stats_max_messages` | `0` | Hard cap on messages stored per group (0 = unlimited) |
| `stats_refresh_interval` | `3600` | Username refresh job interval, seconds |
| `stats_charts_enabled` | `true` | Toggle chart endpoints (off = analytics tables only) |
