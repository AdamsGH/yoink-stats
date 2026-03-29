SELECT username, display_name
FROM stats_user_names
WHERE user_id = :user_id
ORDER BY date DESC
LIMIT 1
