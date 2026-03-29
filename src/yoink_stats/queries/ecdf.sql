WITH per_user AS (
    SELECT
        m.from_user,
        COUNT(m.id) AS cnt,
        un.username,
        un.display_name
    FROM stats_messages m
    LEFT JOIN stats_user_latest_name un ON un.user_id = m.from_user
    WHERE m.chat_id = :chat_id AND m.from_user IS NOT NULL
    GROUP BY m.from_user, un.username, un.display_name
    ORDER BY cnt DESC
    LIMIT :limit
),
total AS (SELECT SUM(cnt) AS grand_total FROM per_user)
SELECT
    p.from_user,
    p.cnt,
    p.username,
    p.display_name,
    ROUND(
        SUM(p.cnt) OVER (ORDER BY p.cnt DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        * 100.0 / NULLIF(t.grand_total, 0),
        1
    ) AS cumulative_pct
FROM per_user p, total t
ORDER BY p.cnt DESC
