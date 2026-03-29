SELECT
    DATE(date AT TIME ZONE 'UTC') AS day,
    COUNT(*) FILTER (WHERE event = 'joined') AS joined,
    COUNT(*) FILTER (WHERE event = 'left') AS left_count
FROM stats_user_events
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY day
ORDER BY day
