SELECT COUNT(id) AS total, MIN(date) AS first_date, MAX(date) AS last_date
FROM stats_messages
WHERE chat_id = :chat_id AND from_user = :user_id
