WITH replies AS (
    SELECT
        r.from_user,
        EXTRACT(EPOCH FROM (r.date - o.date)) AS delay_sec
    FROM stats_messages r
    JOIN stats_messages o
        ON o.chat_id = r.chat_id AND o.message_id = r.reply_to_message
    WHERE r.chat_id = :chat_id
      AND r.reply_to_message IS NOT NULL
      AND r.from_user IS NOT NULL
      AND r.from_user != o.from_user
      AND EXTRACT(EPOCH FROM (r.date - o.date)) BETWEEN 1 AND 86400
      AND (CAST(:since AS timestamptz) IS NULL OR r.date >= :since)
)
SELECT
    rp.from_user AS user_id,
    COALESCE(un.display_name, u.first_name) AS display_name,
    COALESCE(un.username, u.username) AS username,
    COUNT(*) AS reply_count,
    ROUND(AVG(rp.delay_sec)) AS avg_sec,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rp.delay_sec) AS median_sec
FROM replies rp
LEFT JOIN stats_user_latest_name un ON un.user_id = rp.from_user
LEFT JOIN users u ON u.id = rp.from_user
GROUP BY rp.from_user, un.display_name, un.username, u.first_name, u.username
ORDER BY reply_count DESC
LIMIT :limit
