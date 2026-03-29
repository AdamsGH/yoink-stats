SELECT lower(m[1]) AS mention, COUNT(*) AS cnt
FROM stats_messages,
     regexp_matches(COALESCE(text, ''), '@([a-zA-Z0-9_]{4,})', 'g') AS m
WHERE chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
GROUP BY mention
ORDER BY cnt DESC
LIMIT :limit
