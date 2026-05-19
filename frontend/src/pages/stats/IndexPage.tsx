import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { BarChart3, ChevronRight, MessageSquare } from 'lucide-react'

import { groupsApi } from '@core/lib/api'
import { statsApi } from '@stats/api'
import { Avatar, AvatarFallback, AvatarImage, Badge, Card, CardContent, CardHeader, CardTitle, Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle, Skeleton } from '@ui'
import { EmptyState } from '@app'
import { toast } from '@core/components/ui/toast'
import type { StatsGroup } from '@stats/types'

export default function StatsIndexPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [groups, setGroups] = useState<StatsGroup[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    statsApi
      .getGroups()
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
            {loading
              ? t('stats.select_group')
              : `${groups.length} ${groups.length === 1 ? t('stats.group_singular', { defaultValue: 'group' }) : t('stats.group_plural', { defaultValue: 'groups' })}`}
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
                  <Skeleton className="h-5 w-14" />
                </div>
              ))}
            </div>
          ) : groups.length === 0 ? (
            <EmptyState message={t('stats.no_groups')} />
          ) : (
            <div className="divide-y divide-border">
              {groups.map((group) => (
                <div key={group.chat_id} className="px-3 py-1">
                  <Item
                    size="sm"
                    className="py-2.5 rounded-none border-0 cursor-pointer"
                    onClick={() => navigate(`/stats/${group.chat_id}`)}
                  >
                    <ItemMedia variant="icon" className="size-8 shrink-0">
                      <Avatar className="size-8 rounded-md">
                        <AvatarImage src={groupsApi.photoUrl(group.chat_id)} className="rounded-md object-cover" />
                        <AvatarFallback className="size-8 rounded-md bg-primary/10 text-primary">
                          <MessageSquare className="size-4" />
                        </AvatarFallback>
                      </Avatar>
                    </ItemMedia>
                    <ItemContent className="gap-0">
                      <ItemTitle className="leading-snug">{group.title}</ItemTitle>
                      <ItemDescription className="mt-0 leading-snug text-[11px] font-mono">
                        {group.message_count.toLocaleString()} {t('stats.messages_label', { defaultValue: 'messages' })}
                      </ItemDescription>
                    </ItemContent>
                    <ItemActions>
                      <Badge variant="secondary" className="text-xs tabular-nums">
                        {group.message_count.toLocaleString()}
                      </Badge>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </ItemActions>
                  </Item>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
