SELECT
    m.from_user,
    COUNT(m.id) AS cnt,
    COALESCE(un.username, u.username) AS username,
    COALESCE(un.display_name, u.first_name) AS display_name,
    u.photo_url
FROM stats_messages m
LEFT JOIN stats_user_latest_name un ON un.user_id = m.from_user
LEFT JOIN users u ON u.id = m.from_user
WHERE m.chat_id = :chat_id
  AND m.from_user IS NOT NULL
  AND (CAST(:since AS timestamptz) IS NULL OR m.date >= :since)
GROUP BY m.from_user, un.username, un.display_name, u.username, u.first_name, u.photo_url
ORDER BY cnt DESC
LIMIT :limit
