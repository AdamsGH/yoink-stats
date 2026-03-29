SELECT
    ((EXTRACT(DOW FROM date)::int + 6) % 7) AS dow,
    EXTRACT(HOUR FROM date)::int AS hour,
    COUNT(id) AS cnt
FROM stats_messages
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY dow, hour
