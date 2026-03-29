SELECT
    all_users.user_id,
    COALESCE(un.display_name, u.first_name)           AS display_name,
    COALESCE(un.username, u.username)                  AS username,
    u.photo_url,
    COALESCE(msg.message_count, 0)                     AS message_count,
    COALESCE(r.reaction_count, 0)                      AS reaction_count,
    msg.first_seen_at,
    GREATEST(
        COALESCE(msg.last_message_at, 'epoch'::timestamptz),
        COALESCE(r.last_reaction_at,  'epoch'::timestamptz)
    )                                                  AS last_active_at,
    gm.in_chat,
    gm.synced_at
FROM (
    SELECT DISTINCT from_user AS user_id
    FROM stats_messages
    WHERE chat_id = :chat_id AND from_user IS NOT NULL
    UNION
    SELECT DISTINCT user_id
    FROM stats_group_members
    WHERE chat_id = :chat_id
) all_users
LEFT JOIN users u ON u.id = all_users.user_id
LEFT JOIN stats_user_latest_name un ON un.user_id = all_users.user_id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS message_count, MIN(date) AS first_seen_at, MAX(date) AS last_message_at
    FROM stats_messages
    WHERE chat_id = :chat_id AND from_user = all_users.user_id
      AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
) msg ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS reaction_count, MAX(date) AS last_reaction_at
    FROM stats_reactions
    WHERE chat_id = :chat_id AND user_id = all_users.user_id
      AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
) r ON true
LEFT JOIN stats_group_members gm
    ON gm.chat_id = :chat_id AND gm.user_id = all_users.user_id
ORDER BY last_active_at DESC
LIMIT 1000
