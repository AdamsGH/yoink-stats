SELECT
    DATE(date AT TIME ZONE 'UTC') AS day,
    COUNT(id) AS cnt
FROM stats_messages
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY day
ORDER BY day
