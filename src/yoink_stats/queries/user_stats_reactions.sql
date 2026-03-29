SELECT COUNT(*) AS reaction_count
FROM stats_reactions
WHERE chat_id = :chat_id AND user_id = :user_id
