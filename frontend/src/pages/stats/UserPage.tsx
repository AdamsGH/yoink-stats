import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'

import { statsApi } from '@stats/api'
import { formatDateDay } from '@core/lib/utils'
import type { UserStats } from '@stats/types'
import { Button, Card, CardContent, Skeleton } from '@ui'
import { toast } from '@core/components/ui/toast'



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
    statsApi
      .getUserStats(Number(chatId), Number(userId))
      .then((r) => setData(r.data))
      .catch(() => toast.error('Failed to load user stats'))
      .finally(() => setLoading(false))
  }, [chatId, userId])

  const displayName = data?.display_name ?? data?.username ?? `User ${userId}`

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/stats/${chatId}`)}>
          ← {groupTitle}
        </Button>
        <span className="text-sm font-medium">
          {loading ? <Skeleton className="h-5 w-40 inline-block" /> : displayName}
        </span>
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
              {t('stats.no_messages')}
            </div>
          ) : (
            <>
              <StatRow label={t('stats.total_messages')} value={data.total} />
              <StatRow label={t('stats.avg_per_day')} value={data.avg_per_day} />
              <StatRow label={t('stats.top_type')} value={data.top_type} />
              <StatRow label={t('stats.first_message_user')} value={formatDateDay(data.first_date)} />
              <StatRow label={t('stats.last_message_user')} value={formatDateDay(data.last_date)} />
              {data.username && (
                <StatRow label={t('stats.username_label')} value={`@${data.username}`} />
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
