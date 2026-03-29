SELECT
    r.user_id,
    COALESCE(un.display_name, u.first_name) AS display_name,
    COALESCE(un.username, u.username) AS username,
    u.photo_url,
    COUNT(*) AS reaction_count
FROM stats_reactions r
LEFT JOIN users u ON u.id = r.user_id
LEFT JOIN stats_user_latest_name un ON un.user_id = r.user_id
WHERE r.chat_id = :chat_id
  AND (CAST(:since AS timestamptz) IS NULL OR r.date >= :since)
GROUP BY r.user_id, u.first_name, u.username, u.photo_url, un.username, un.display_name
ORDER BY reaction_count DESC
LIMIT :limit
