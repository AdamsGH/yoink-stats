import { apiClient } from '@core/lib/api-client'
import type { UserStats } from '@core/types/plugin'

export interface DlOverview {
  total?: number
  this_week?: number
  today?: number
  top_domains?: Array<{ domain: string; count: number }>
  downloads_by_day?: Array<{ date: string; count: number }>
  [key: string]: unknown
}

export interface InsightStats {
  total_summaries: number
  total?: number
  this_week: number
  today: number
  by_command?: Record<string, number>
  by_day?: Array<{ date: string; count: number }>
  [key: string]: unknown
}

export interface MusicStats {
  total: number
  this_week: number
  today: number
  top_platforms?: Array<{ platform: string; count: number }>
  top_artists?: Array<{ artist: string; count: number }>
  by_day?: Array<{ date: string; count: number }>
  [key: string]: unknown
}

export const meApi = {
  getStats: (statsEndpoint: string) =>
    apiClient.get<UserStats>(statsEndpoint),

  getDlOverview: (days = 30) =>
    apiClient.get<DlOverview>('/dl/stats/overview', { params: { days } }),

  getInsightStats: () =>
    apiClient.get<InsightStats>('/insight/me/stats'),

  getMusicStats: () =>
    apiClient.get<MusicStats>('/music/me/stats'),
}
