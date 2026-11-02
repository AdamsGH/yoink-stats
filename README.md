# Yoink Stats

Stats adds group analytics and message search to [Yoink](https://github.com/AdamsGH/yoink-core). Native Rust services own ingestion, authorization, analytics, and the derived Tantivy index.

This repository contains the Stats frontend and retained legacy Python implementation. It is not an independent service in the native deployment.

## Use

```text
/stats counts -n 10
/stats types
/stats words -n 20
/stats history --days 7
/stats user
```

Run `/stats` in a group for command help. Private chats support only authorized `user` summaries.

The Mini App provides group dashboards, activity views, member statistics, and related analytics.

## Data and access

Normal ingestion excludes private messages, disabled groups, and bot commands. The Bot API does not report ordinary message deletions.

Access depends on current identity, local assignments, Telegram membership, and the operation. Synchronization and administration have stricter requirements than ordinary analytics.

The search contract is explicit and differs from PostgreSQL full-text tokenization. Native application rows remain the source of truth.

## Configuration

Native settings include `YOINK_RUST_STATS_INDEX_DIR`, `YOINK_RUST_STATS_REFRESH_INTERVAL_SECS`, and `YOINK_RUST_STATS_IMPORT_ROOT`.

The retained lowercase Python settings do not configure the Rust service. Declared legacy retention or chart options are not evidence of native support.

## Documentation

- [Stats guide](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/stats.md)
- [Search contract](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/stats-search.md)
- [Product limits](https://github.com/AdamsGH/yoink-core/blob/master/docs/architecture/products.md)
- [Installation](https://github.com/AdamsGH/yoink-core/blob/master/docs/operations/installation.md)
