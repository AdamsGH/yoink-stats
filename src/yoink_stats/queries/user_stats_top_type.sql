SELECT msg_type, COUNT(id) AS cnt
FROM stats_messages
WHERE chat_id = :chat_id AND from_user = :user_id
GROUP BY msg_type
ORDER BY cnt DESC
LIMIT 1
