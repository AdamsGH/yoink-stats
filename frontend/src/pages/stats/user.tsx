import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'

import { apiClient } from '@core/lib/api-client'
import { Button } from '@core/components/ui/button'
import { Card, CardContent } from '@core/components/ui/card'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'

interface UserStats {
  user_id: number
  username: string | null
  display_name: string | null
  total: number
  first_date: string | null
  last_date: string | null
  avg_per_day: number
  top_type: string | null
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function StatRow({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium tabular-nums">
        {value === null || value === undefined ? '-' : typeof value === 'number' ? value.toLocaleString() : value}
      </span>
    </div>
  )
}

export default function StatsUserPage() {
  const { t } = useTranslation()
  const { chatId, userId } = useParams<{ chatId: string; userId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const groupTitle = searchParams.get('group') ?? `Group ${chatId}`

  const [data, setData] = useState<UserStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!chatId || !userId) return
    apiClient
      .get<UserStats>('/stats/user-stats', { params: { chat_id: chatId, user_id: userId } })
      .then((r) => setData(r.data))
      .catch(() => toast.error('Failed to load user stats'))
      .finally(() => setLoading(false))
  }, [chatId, userId])

  const displayName = data?.display_name ?? data?.username ?? `User ${userId}`

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/stats/${chatId}`)}>
          ← {groupTitle}
        </Button>
        <h1 className="text-2xl font-bold">
          {loading ? <Skeleton className="h-7 w-48" /> : displayName}
        </h1>
      </div>

      <Card>
        <CardContent className="pt-5">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-5 w-full" />
              ))}
            </div>
          ) : !data || data.total === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No messages from this user in this group.
            </div>
          ) : (
            <>
              <StatRow label={t('stats.total_messages')} value={data.total} />
              <StatRow label="Avg / day" value={data.avg_per_day} />
              <StatRow label="Most used type" value={data.top_type} />
              <StatRow label="First message" value={formatDate(data.first_date)} />
              <StatRow label="Last message" value={formatDate(data.last_date)} />
              {data.username && (
                <StatRow label="Username" value={`@${data.username}`} />
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
