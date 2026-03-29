SELECT
    DATE(date AT TIME ZONE 'UTC') AS day,
    COUNT(id) AS messages,
    COUNT(DISTINCT from_user) FILTER (WHERE from_user IS NOT NULL) AS dau
FROM stats_messages
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY day
ORDER BY day
