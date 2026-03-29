SELECT reaction_key, reaction_type, COUNT(*) AS cnt
FROM stats_reactions r
WHERE chat_id = :chat_id
  AND reaction_type IN ('emoji', 'custom_emoji')
  AND (CAST(:since AS timestamptz) IS NULL OR r.date >= :since)
GROUP BY reaction_key, reaction_type
ORDER BY cnt DESC
LIMIT :limit
