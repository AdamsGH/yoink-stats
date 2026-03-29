import { apiClient } from '@core/lib/api-client'

export interface ImportStatus {
  job_id: string
  status: 'pending' | 'running' | 'done' | 'error'
  progress?: number
  inserted: number
  skipped: number
  events: number
  processed: number
  total: number
  message?: string | null
  error: string | null
}

export const importApi = {
  getStatus: (jobId: string) =>
    apiClient.get<ImportStatus>(`/stats/import/${jobId}`),

  startFromFile: (
    formData: FormData,
    chatId: number,
    onUploadProgress?: (e: { loaded: number; total?: number }) => void
  ) =>
    apiClient.post<ImportStatus>(`/stats/import?chat_id=${chatId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600_000,
      onUploadProgress,
    }),

  startFromPath: (path: string, chatId?: number) =>
    apiClient.post<ImportStatus>('/stats/import/by-path', { path, chat_id: chatId }),
}
