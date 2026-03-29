SELECT m.date, m.new_chat_title, m.from_user, un.username, un.display_name
FROM stats_messages m
LEFT JOIN stats_user_latest_name un ON un.user_id = m.from_user
WHERE m.chat_id = :chat_id AND m.msg_type = 'new_chat_title'
ORDER BY m.date
