SELECT DISTINCT from_user FROM stats_messages WHERE chat_id = :chat_id AND from_user IS NOT NULL
