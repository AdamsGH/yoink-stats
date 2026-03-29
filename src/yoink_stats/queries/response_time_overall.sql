SELECT
    ROUND(AVG(delay)) AS avg_sec,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay) AS median_sec,
    COUNT(*) AS total_replies
FROM (
    SELECT EXTRACT(EPOCH FROM (r.date - o.date)) AS delay
    FROM stats_messages r
    JOIN stats_messages o
        ON o.chat_id = r.chat_id AND o.message_id = r.reply_to_message
    WHERE r.chat_id = :chat_id
      AND r.reply_to_message IS NOT NULL
      AND r.from_user IS NOT NULL
      AND r.from_user != COALESCE(o.from_user, 0)
      AND EXTRACT(EPOCH FROM (r.date - o.date)) BETWEEN 1 AND 86400
      AND (CAST(:since AS timestamptz) IS NULL OR r.date >= :since)
) sub
