import { apiClient } from '@core/lib/api-client'

export interface ThreadsStatus {
  available: boolean
}

export const threadsApi = {
  getStatus: () =>
    apiClient.get<ThreadsStatus>('/threads/status'),
}
