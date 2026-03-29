import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { BarChart3, ChevronRight, MessageSquare } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@core/components/ui/item'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import type { StatsGroup } from '@stats/types'

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
    <div className="space-y-4">
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            {t('stats.select_group')}
          </CardTitle>
        </CardHeader>

        <CardContent className="p-0">
          {loading ? (
            <div className="divide-y divide-border px-3 py-1">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 py-2.5">
                  <Skeleton className="size-8 rounded-md shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-36" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-4 w-4" />
                </div>
              ))}
            </div>
          ) : groups.length === 0 ? (
            <div className="flex justify-center py-12 text-sm text-muted-foreground">
              {t('stats.no_groups')}
            </div>
          ) : (
            <div className="divide-y divide-border px-3 py-1">
              {groups.map((group) => (
                <Item
                  key={group.chat_id}
                  size="sm"
                  className="py-2.5 rounded-none border-0 cursor-pointer"
                  onClick={() => navigate(`/stats/${group.chat_id}`)}
                >
                  <ItemMedia
                    variant="icon"
                    className="size-8 rounded-md bg-primary/10 text-primary"
                  >
                    <MessageSquare className="size-4" />
                  </ItemMedia>
                  <ItemContent>
                    <ItemTitle>{group.title}</ItemTitle>
                    <ItemDescription>
                      {t('stats.messages_count', { count: group.message_count })}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </ItemActions>
                </Item>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
