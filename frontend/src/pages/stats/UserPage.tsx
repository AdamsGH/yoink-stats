import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import {
  ArrowLeft, Calendar, CalendarDays, Clock,
  ExternalLink, Hash, MessageSquare, ThumbsUp, Type,
} from 'lucide-react'

import { statsApi } from '@stats/api'
import { formatDateDay } from '@core/lib/utils'
import { openProfileLink, userInitials, userPhotoUrl } from '@core/lib/user-utils'
import type { UserStats } from '@stats/types'
import { Avatar, AvatarFallback, AvatarImage, Button, Card, CardContent, CardHeader, CardTitle, Skeleton } from '@ui'
import { toast } from '@core/components/ui/toast'
import { StatCard, StatCardSkeleton } from '@core/components/charts'

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number | null }) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
      <span className="text-muted-foreground shrink-0">{icon}</span>
      <span className="text-sm text-muted-foreground flex-1">{label}</span>
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
  const initials = userInitials({ first_name: data?.display_name, username: data?.username })
  const photoUrl = userId ? userPhotoUrl(Number(userId)) : undefined

  return (
    <div className="space-y-4">
      {/* Back button */}
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => navigate(`/stats/${chatId}`)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <span className="text-sm text-muted-foreground truncate">{groupTitle}</span>
      </div>

      {/* User header card */}
      <Card>
        <CardContent className="pt-5 pb-4">
          {loading ? (
            <div className="flex items-center gap-4">
              <Skeleton className="size-14 rounded-full shrink-0" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-5 w-36" />
                <Skeleton className="h-3.5 w-24" />
              </div>
            </div>
          ) : !data || data.total === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t('stats.no_messages')}
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <Avatar className="size-14 ring-2 ring-border shadow-sm shrink-0">
                <AvatarImage src={photoUrl} />
                <AvatarFallback className="text-lg font-bold">{initials}</AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="font-semibold text-base truncate">{displayName}</p>
                  {(data.username || userId) && (
                    <button
                      onClick={() => openProfileLink(data.user_id, data.username)}
                      className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                      title={data.username ? `@${data.username}` : `ID: ${userId}`}
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                {data.username && (
                  <p className="text-sm text-muted-foreground">@{data.username}</p>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* KPI cards */}
      {loading ? (
        <div className="grid grid-cols-3 gap-2">
          {Array.from({ length: 3 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
      ) : data && data.total > 0 ? (
        <div className="grid grid-cols-3 gap-2">
          <StatCard centered icon={<MessageSquare className="h-4 w-4" />} label={t('stats.total_messages')} value={data.total} />
          <StatCard centered icon={<Hash className="h-4 w-4" />} label={t('stats.avg_per_day')} value={data.avg_per_day} />
          {(data.reaction_count ?? 0) > 0
            ? <StatCard centered icon={<ThumbsUp className="h-4 w-4" />} label="Reactions" value={data.reaction_count!} />
            : <StatCard centered icon={<Type className="h-4 w-4" />} label={t('stats.top_type')} value={data.top_type ?? '-'} />
          }
        </div>
      ) : null}

      {/* Detail rows */}
      {!loading && data && data.total > 0 && (
        <Card>
          <CardHeader className="px-4 py-3">
            <CardTitle className="text-sm font-medium">{t('stats.details', { defaultValue: 'Details' })}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-2 pt-0">
            {(data.reaction_count ?? 0) > 0 && (
              <DetailRow icon={<Type className="h-4 w-4" />} label={t('stats.top_type')} value={data.top_type ?? '-'} />
            )}
            <DetailRow icon={<CalendarDays className="h-4 w-4" />} label={t('stats.first_message_user')} value={formatDateDay(data.first_date)} />
            <DetailRow icon={<Clock className="h-4 w-4" />} label={t('stats.last_message_user')} value={formatDateDay(data.last_date)} />
            {data.username && (
              <DetailRow icon={<Calendar className="h-4 w-4" />} label={t('stats.username_label')} value={`@${data.username}`} />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
