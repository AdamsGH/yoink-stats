SELECT
    TO_CHAR(date AT TIME ZONE 'UTC', 'YYYY-MM') AS month,
    COUNT(*) FILTER (WHERE msg_type = 'text') AS text_count,
    COUNT(*) FILTER (WHERE msg_type != 'text') AS media_count,
    COUNT(*) AS total
FROM stats_messages
WHERE chat_id = :chat_id
  AND from_user IS NOT NULL
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY month
ORDER BY month
