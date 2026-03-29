WITH messages AS (
    SELECT COALESCE(text, '') || ' ' || COALESCE(caption, '') AS body
    FROM stats_messages
    WHERE chat_id = :chat_id
      AND (text IS NOT NULL OR caption IS NOT NULL)
      AND (CAST(:since AS timestamptz) IS NULL OR date >= :since)
),
words AS (
    SELECT lower(regexp_replace(w, '[^\w]|[\d_]', '', 'g')) AS word
    FROM messages,
         regexp_split_to_table(body, '\s+') AS w
    WHERE char_length(regexp_replace(w, '[^\w]|[\d_]', '', 'g')) >= 3
)
SELECT word, COUNT(*) AS cnt
FROM words
WHERE word NOT IN (
    'the','a','an','in','on','at','to','of','is','it','and','or',
    'but','for','with','это','как','что','так','все','там','уже',
    'мне','его','она','они','ещё','был','не','да','же','вот','то',
    'из','он','по','до','во','от','со','при','за','над','под','для'
)
  AND word <> ''
GROUP BY word
ORDER BY cnt DESC
LIMIT :limit
