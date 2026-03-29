import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'

import { statsApi } from '@stats/api'
import { openProfileLink, userInitials, userPhotoUrl } from '@core/lib/user-utils'
import type { DrawerUser, UserStats } from '@stats/types'
import { Avatar, AvatarFallback, AvatarImage, Badge, Drawer, DrawerContent, Skeleton } from '@ui'

interface UserStatsDrawerProps {
  user: DrawerUser | null
  chatId: number
  onClose: () => void
}

export function UserStatsDrawer({ user, chatId, onClose }: UserStatsDrawerProps) {
  const [stats, setStats] = useState<UserStats | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!user) { setStats(null); return }
    setLoading(true)
    statsApi.getUserStats(chatId, user.user_id)
      .then((r) => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [user?.user_id, chatId])

  const label = user?.display_name ?? user?.username ?? (user ? String(user.user_id) : '')
  const initials = userInitials({ first_name: user?.display_name, username: user?.username })
  const photoUrl = user ? userPhotoUrl(user.user_id) : undefined
  const m = user?.member ?? null

  const rows: [string, string][] = user ? [
    ['User ID', String(user.user_id)],
    ...(m ? [
      ['Messages', m.message_count.toLocaleString()] as [string, string],
      ['Reactions given', m.reaction_count > 0 ? m.reaction_count.toLocaleString() : '—'] as [string, string],
    ] : [
      ['Messages', stats?.total != null ? stats.total.toLocaleString() : '—'] as [string, string],
    ]),
    ['Avg / day', stats?.avg_per_day != null ? String(stats.avg_per_day) : '—'],
    ['Top type', stats?.top_type ?? '—'],
    ['First seen', stats?.first_date ? new Date(stats.first_date).toLocaleDateString() : '—'],
    ['Last active', (m?.last_active_at ?? stats?.last_date)
      ? new Date((m?.last_active_at ?? stats!.last_date)!).toLocaleDateString()
      : '—'],
  ] : []

  return (
    <Drawer open={!!user} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent className="max-h-[80vh] border-0">
        {user && (
          <>
            <div className="bg-gradient-to-b from-muted/60 to-background -mt-7 pt-7 px-4 pb-4 border-b border-border/50 rounded-t-[10px]">
              <div className="flex items-center gap-4">
                <Avatar className="size-14 ring-2 ring-border shadow-md">
                  <AvatarImage src={photoUrl} />
                  <AvatarFallback className="text-lg font-bold">{initials}</AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="font-semibold text-base truncate">{label}</p>
                    <button
                      onClick={() => openProfileLink(user.user_id, user.username)}
                      className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                      title={user.username ? `@${user.username}` : `ID: ${user.user_id}`}
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  {user.username && <p className="text-sm text-muted-foreground">@{user.username}</p>}
                  {m && (
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant={m.is_active ? 'default' : 'secondary'} className="text-xs px-1.5 py-0">
                        {m.is_active ? 'active' : 'inactive'}
                      </Badge>
                      {m.in_chat === true && <Badge variant="outline" className="text-xs px-1.5 py-0">in chat</Badge>}
                      {m.in_chat === false && <Badge variant="outline" className="text-xs px-1.5 py-0 text-muted-foreground">left</Badge>}
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="overflow-y-auto px-4 py-3 space-y-1">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)
              ) : (
                rows.map(([lbl, val]) => (
                  <div key={lbl} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                    <span className="text-sm text-muted-foreground">{lbl}</span>
                    <span className="text-sm font-medium tabular-nums">{val}</span>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </DrawerContent>
    </Drawer>
  )
}
