import { apiClient } from '@core/lib/api-client'
import type {
  StatsGroup,
  StatsOverview,
  TopUser,
  HourActivity,
  DayActivity,
  MessageType,
  WordCount,
  MonthActivity,
  MentionStat,
  AvgMessageLength,
  ResponseTimeData,
  MediaTrend,
  Member,
  UserStats,
} from '@stats/types'



export interface TopReactionGiver {
  user_id: number
  username: string | null
  display_name: string | null
  has_photo?: boolean
  count: number
  reaction_count?: number
}

export interface TopEmoji {
  emoji?: string
  count: number
  reaction_type?: string
  reaction_key?: string
}

export interface TopReactions {
  top_givers: TopReactionGiver[]
  top_emoji: TopEmoji[]
}

export type StatsParams = Record<string, number | string | undefined>

export const statsApi = {
  getOverview: (params: StatsParams) =>
    apiClient.get<StatsOverview>('/stats/overview', { params }),

  getGroups: () =>
    apiClient.get<StatsGroup[]>('/stats/groups'),

  getTopUsers: (params: StatsParams & { limit?: number }) =>
    apiClient.get<TopUser[]>('/stats/top-users', { params }),

  getActivityByHour: (params: StatsParams) =>
    apiClient.get<HourActivity[]>('/stats/activity-by-hour', { params }),

  getActivityByDay: (params: StatsParams) =>
    apiClient.get<DayActivity[]>('/stats/activity-by-day', { params }),

  getActivityByMonth: (params: StatsParams) =>
    apiClient.get<MonthActivity[]>('/stats/activity-by-month', { params }),

  getDailyActivity: (params: StatsParams) =>
    apiClient.get<unknown[]>('/stats/daily-activity', { params }),

  getMessageTypes: (params: StatsParams) =>
    apiClient.get<MessageType[]>('/stats/message-types', { params }),

  getWords: (params: StatsParams & { limit?: number }) =>
    apiClient.get<WordCount[]>('/stats/words', { params }),

  getMentions: (params: StatsParams & { limit?: number }) =>
    apiClient.get<MentionStat[]>('/stats/mention-stats', { params }),

  getMemberEvents: (params: StatsParams) =>
    apiClient.get<unknown[]>('/stats/member-events', { params }),

  getAvgMessageLength: (params: StatsParams & { limit?: number }) =>
    apiClient.get<AvgMessageLength[]>('/stats/avg-message-length', { params }),

  getResponseTime: (params: StatsParams & { limit?: number }) =>
    apiClient.get<ResponseTimeData>('/stats/response-time', { params }),

  getMediaTrend: (params: StatsParams) =>
    apiClient.get<MediaTrend[]>('/stats/media-trend', { params }),

  getTopReactions: (params: StatsParams & { limit?: number }) =>
    apiClient.get<TopReactions>('/stats/top-reactions', { params }),

  getMembers: (params: { chat_id: number | Record<string, number> }) =>
    apiClient.get<Member[]>('/stats/members', { params }),

  syncMembers: (chatId: number) =>
    apiClient.post<Member[]>('/stats/members/sync', null, { params: { chat_id: chatId } }),

  getChatAdmins: (chatId: number) =>
    apiClient.get<Array<{ user_id: number; status: string }>>('/stats/chat-admins', {
      params: { chat_id: chatId },
    }),

  getUserStats: (chatId: number, userId: number) =>
    apiClient.get<UserStats>('/stats/user-stats', { params: { chat_id: chatId, user_id: userId } }),
}
