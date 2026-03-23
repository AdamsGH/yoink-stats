import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { apiClient } from '@core/lib/api-client'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import type { StatsGroup } from '@stats/types'

function GroupCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-40" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-28" />
      </CardContent>
    </Card>
  )
}

export default function StatsIndexPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [groups, setGroups] = useState<StatsGroup[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient
      .get<StatsGroup[]>('/stats/groups')
      .then((res) => {
        const data = res.data
        if (data.length === 1) {
          navigate(`/stats/${data[0].chat_id}`, { replace: true })
          return
        }
        setGroups(data)
      })
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => setLoading(false))
  }, [navigate])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('stats.title')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('stats.select_group')}</p>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <GroupCardSkeleton key={i} />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          No monitored groups yet. Use /group stats on in a group to enable stats.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => (
            <Card key={group.chat_id} className="flex flex-col">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{group.title}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col justify-between gap-3">
                <div className="text-sm text-muted-foreground">
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium tabular-nums">
                    {group.message_count.toLocaleString()} messages
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="self-start"
                  onClick={() => navigate(`/stats/${group.chat_id}`)}
                >
                  View stats →
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
