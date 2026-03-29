import { useMemo, useState } from 'react'
import { ArrowDownAZ, ArrowUpAZ, RefreshCw, Search } from 'lucide-react'

import { statsApi } from '@stats/api'
import { userInitials, userPhotoUrl } from '@core/lib/user-utils'
import type { DrawerUser, Member } from '@stats/types'
import type { Period } from '@core/components/charts'
import { Avatar, AvatarFallback, AvatarImage, Badge, Button, Card, CardContent, CardHeader, Input, Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle, Skeleton } from '@ui'
import { InlineSelect } from '@app'
import { toast } from '@core/components/ui/toast'
import { UserStatsDrawer } from './UserStatsDrawer'

function memberLabel(m: Member) { return m.display_name ?? m.username ?? String(m.user_id) }

function formatRelative(iso: string | null): string | null {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

interface MembersTabProps {
  chatId: number
  members: Member[] | null
  loading: boolean
  onLoad: (members: Member[]) => void
  sessionAvailable: boolean
  period: Period
}

export function MembersTab({ chatId, members, loading, onLoad, sessionAvailable, period: _period }: MembersTabProps) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [chatFilter, setChatFilter] = useState<'any' | 'in_chat' | 'left'>('any')
  const [syncing, setSyncing] = useState(false)
  const [sortBy, setSortBy] = useState<'last_active' | 'messages' | 'reactions' | 'name' | 'joined'>('last_active')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
  const [selected, setSelected] = useState<DrawerUser | null>(null)

  function handleSync() {
    setSyncing(true)
    statsApi.syncMembers(chatId)
      .then((r) => onLoad(r.data))
      .catch(() => toast.error('Sync failed'))
      .finally(() => setSyncing(false))
  }

  const hasChatInfo = (members ?? []).some((m) => m.in_chat === true || m.in_chat === false)

  const filtered = useMemo(() => {
    const list = (members ?? []).filter((m) => {
      if (filter === 'active' && !m.is_active) return false
      if (filter === 'inactive' && m.is_active) return false
      if (chatFilter === 'in_chat' && m.in_chat !== true) return false
      if (chatFilter === 'left' && m.in_chat !== false) return false
      if (!search) return true
      const q = search.toLowerCase()
      return (
        (m.display_name ?? '').toLowerCase().includes(q) ||
        (m.username ?? '').toLowerCase().includes(q) ||
        String(m.user_id).includes(q)
      )
    })

    const dir = sortDir === 'desc' ? -1 : 1
    list.sort((a, b) => {
      switch (sortBy) {
        case 'messages':    return dir * (a.message_count - b.message_count)
        case 'reactions':   return dir * (a.reaction_count - b.reaction_count)
        case 'name':        return dir * (memberLabel(a).localeCompare(memberLabel(b)))
        case 'joined':      return dir * ((a.first_seen_at ?? '').localeCompare(b.first_seen_at ?? ''))
        case 'last_active':
        default:            return dir * ((a.last_active_at ?? '').localeCompare(b.last_active_at ?? ''))
      }
    })
    return list
  }, [members, filter, chatFilter, search, sortBy, sortDir])

  return (
    <>
      <Card>
        <CardHeader className="px-4 py-3 gap-2">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search members..."
                className="h-8 pl-8 text-sm"
              />
            </div>
            {sessionAvailable && (
              <Button variant="outline" size="sm" className="h-8 px-2.5 text-xs shrink-0" onClick={handleSync} disabled={syncing}>
                <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : 'Sync all'}
              </Button>
            )}
          </div>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex rounded-md border text-xs">
                {(['all', 'active', 'inactive'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`h-7 px-2.5 capitalize transition-colors first:rounded-l-md last:rounded-r-md ${filter === f ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
                  >
                    {f}
                  </button>
                ))}
              </div>
              {hasChatInfo && (
                <div className="flex rounded-md border text-xs">
                  {(['any', 'in_chat', 'left'] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setChatFilter(f)}
                      className={`h-7 px-2.5 transition-colors first:rounded-l-md last:rounded-r-md ${chatFilter === f ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
                    >
                      {f === 'any' ? 'Any' : f === 'in_chat' ? 'In chat' : 'Left'}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <InlineSelect
                options={[
                  { value: 'last_active', label: 'Last active' },
                  { value: 'messages',    label: 'Messages' },
                  { value: 'reactions',   label: 'Reactions' },
                  { value: 'name',        label: 'Name' },
                  { value: 'joined',      label: 'First seen' },
                ]}
                value={sortBy}
                onValueChange={(v) => setSortBy(v as typeof sortBy)}
                className="h-7 text-xs w-32"
              />
              <button
                onClick={() => setSortDir((d) => d === 'desc' ? 'asc' : 'desc')}
                className="h-7 w-7 flex items-center justify-center rounded-md border hover:bg-muted/50 transition-colors"
                title={sortDir === 'desc' ? 'Descending' : 'Ascending'}
              >
                {sortDir === 'desc'
                  ? <ArrowDownAZ className="h-3.5 w-3.5" />
                  : <ArrowUpAZ className="h-3.5 w-3.5" />}
              </button>
              {members && (
                <p className="text-xs text-muted-foreground pl-1">
                  {filtered.length}/{
                    chatFilter === 'in_chat' ? members.filter(m => m.in_chat === true).length
                    : chatFilter === 'left'  ? members.filter(m => m.in_chat === false).length
                    : members.length
                  }
                  {!sessionAvailable && <span className="ml-1 opacity-60">·&nbsp;senders</span>}
                </p>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-2 py-0 pb-2">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-2 py-2">
                <Skeleton className="h-9 w-9 rounded-full shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            ))
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No members found</p>
          ) : (
            filtered.map((m) => (
              <Item
                key={m.user_id}
                className="px-2 cursor-pointer"
                onClick={() => setSelected({ user_id: m.user_id, username: m.username, display_name: m.display_name, member: m })}
              >
                <ItemMedia>
                  <Avatar className="h-9 w-9">
                    <AvatarImage src={userPhotoUrl(m.user_id)} />
                    <AvatarFallback className="text-xs">{userInitials({ first_name: m.display_name, username: m.username })}</AvatarFallback>
                  </Avatar>
                </ItemMedia>
                <ItemContent>
                  <ItemTitle className="text-sm">{memberLabel(m)}</ItemTitle>
                  <ItemDescription className="text-xs">
                    {m.message_count.toLocaleString()} msgs
                    {m.reaction_count > 0 && ` · ${m.reaction_count.toLocaleString()} ❤`}
                    {m.last_active_at && ` · ${formatRelative(m.last_active_at)}`}
                  </ItemDescription>
                </ItemContent>
                <ItemActions className="flex-col items-end gap-1">
                  <Badge variant={m.is_active ? 'default' : 'secondary'} className="text-xs px-1.5 py-0.5">
                    {m.is_active ? 'active' : 'inactive'}
                  </Badge>
                  {m.in_chat === false && (
                    <Badge variant="outline" className="text-xs px-1.5 py-0.5 text-muted-foreground">
                      left
                    </Badge>
                  )}
                </ItemActions>
              </Item>
            ))
          )}
        </CardContent>
      </Card>
      <UserStatsDrawer user={selected} chatId={chatId} onClose={() => setSelected(null)} />
    </>
  )
}
