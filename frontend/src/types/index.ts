export interface StatsGroup {
  chat_id: number
  title: string
  message_count: number
}

export interface StatsOverview {
  chat_id: number
  total_messages: number
  unique_users: number
  total_reactions: number
  first_date: string | null
  last_date: string | null
}

export interface TopUser {
  user_id: number
  username: string | null
  display_name: string | null
  count: number
  has_photo?: boolean
}

export interface HourActivity { hour: number; count: number }
export interface DayActivity { day: number; count: number }
export interface MessageType { type: string; count: number }
export interface DailyHistory { date: string; count: number }
export interface WordCount { word: string; count: number }
export interface MonthActivity { month: string; count: number }
export interface MentionStat { mention: string; count: number }

export interface AvgMessageLength {
  user_id: number
  display_name: string | null
  username: string | null
  total: number
  avg_len: number
  max_len: number
}

export interface ResponseTimeUser {
  user_id: number
  display_name: string | null
  username: string | null
  reply_count: number
  avg: string
  median: string
}

export interface ResponseTimeData {
  overall_avg: string
  overall_median: string
  total_replies: number
  users: ResponseTimeUser[]
}

export interface MediaTrend {
  month: string
  text: number
  media: number
  total: number
  media_pct: number
}
