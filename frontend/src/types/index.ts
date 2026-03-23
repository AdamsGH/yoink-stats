export interface StatsGroup {
  chat_id: number
  title: string
  message_count: number
}

export interface StatsOverview {
  chat_id: number
  total_messages: number
  unique_users: number
  first_date: string | null
  last_date: string | null
}

export interface TopUser {
  user_id: number
  username: string | null
  display_name: string | null
  count: number
}

export interface HourActivity { hour: number; count: number }
export interface DayActivity { day: number; count: number }
export interface MessageType { type: string; count: number }
export interface DailyHistory { date: string; count: number }
export interface WordCount { word: string; count: number }
export interface MonthActivity { month: string; count: number }
export interface MentionStat { mention: string; count: number }
