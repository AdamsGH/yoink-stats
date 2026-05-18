DELETE FROM stats_chat_admins WHERE chat_id = :chat_id AND user_id NOT IN :ids
