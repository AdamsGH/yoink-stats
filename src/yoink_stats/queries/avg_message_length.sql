SELECT
    m.from_user AS user_id,
    COALESCE(un.display_name, u.first_name) AS display_name,
    COALESCE(un.username, u.username) AS username,
    COUNT(*) AS total,
    ROUND(AVG(LENGTH(COALESCE(m.text, m.caption, '')))) AS avg_len,
    MAX(LENGTH(COALESCE(m.text, m.caption, ''))) AS max_len
FROM stats_messages m
LEFT JOIN stats_user_latest_name un ON un.user_id = m.from_user
LEFT JOIN users u ON u.id = m.from_user
WHERE m.chat_id = :chat_id
  AND m.from_user IS NOT NULL
  AND COALESCE(m.text, m.caption) IS NOT NULL
  AND (CAST(:since AS timestamptz) IS NULL OR m.date >= :since)
GROUP BY m.from_user, un.display_name, un.username, u.first_name, u.username
ORDER BY total DESC
LIMIT :limit
