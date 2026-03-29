SELECT
    TO_CHAR(DATE_TRUNC('month', date), 'YYYY-MM') AS month,
    COUNT(id) AS cnt
FROM stats_messages
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY month
ORDER BY month
