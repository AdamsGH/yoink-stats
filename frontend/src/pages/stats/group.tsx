import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { useGetIdentity } from '@refinedev/core'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@core/components/ui/tabs'
import ImportPage from '@stats/pages/import/index'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ArrowLeft, Calendar, Clock, Download, MessageSquare, RefreshCw, Search, Type, Users as UsersIcon } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { Avatar, AvatarFallback, AvatarImage } from '@core/components/ui/avatar'
import { Badge } from '@core/components/ui/badge'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Drawer, DrawerContent } from '@core/components/ui/drawer'
import { Input } from '@core/components/ui/input'
import { Item, ItemActions, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@core/components/ui/item'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import { chartColors, PeriodToggle, StatCard, StatCardSkeleton } from '@core/components/charts'
import type { Period } from '@core/components/charts'
import type {
  DayActivity,
  HourActivity,
  MentionStat,
  MessageType,
  MonthActivity,
  StatsGroup,
  StatsOverview,
  TopUser,
  WordCount,
  AvgMessageLength,
  ResponseTimeData,
  MediaTrend,
} from '@stats/types'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })
}

function userLabel(u: TopUser): string {
  return u.display_name ?? u.username ?? String(u.user_id)
}

function userInitials(u: TopUser): string {
  const name = u.display_name ?? u.username ?? ''
  return name.slice(0, 2).toUpperCase() || '#'
}

function userPhotoUrl(u: TopUser): string | undefined {
  if (!u.has_photo) return undefined
  return `${apiClient.defaults.baseURL}/users/${u.user_id}/photo`
}

function formatMonthLabel(month: string): string {
  const [year, mon] = month.split('-')
  const date = new Date(Number(year), Number(mon) - 1, 1)
  return date.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

interface DailyActivity {
  date: string
  messages: number
  dau: number
}

interface MemberEvent {
  date: string
  joined: number
  left: number
}

interface GroupData {
  overview: StatsOverview
  topUsers: TopUser[]
  byHour: HourActivity[]
  byDay: DayActivity[]
  types: MessageType[]
  words: WordCount[]
  byMonth: MonthActivity[]
  mentions: MentionStat[]
  avgLength: AvgMessageLength[]
  responseTime: ResponseTimeData | null
  mediaTrend: MediaTrend[]
}

interface PeriodData {
  daily: DailyActivity[]
  memberEvents: MemberEvent[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function RankedList({ items, labelKey, valueKey, limit = 10 }: {
  items: any[]
  labelKey: string
  valueKey: string
  limit?: number
}) {
  const top = items.slice(0, limit)
  if (top.length === 0) return <p className="text-sm text-muted-foreground text-center py-4">No data</p>
  const max = Math.max(...top.map((i) => Number(i[valueKey]) || 0))
  return (
    <div className="space-y-1.5">
      {top.map((item, i) => {
        const val = Number(item[valueKey]) || 0
        const pct = max > 0 ? (val / max) * 100 : 0
        return (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="w-5 text-right text-xs text-muted-foreground tabular-nums">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-xs">{String(item[labelKey])}</span>
                <span className="tabular-nums text-xs text-muted-foreground shrink-0">{val.toLocaleString()}</span>
              </div>
              <div className="h-1 rounded-full bg-muted mt-0.5">
                <div
                  className="h-full rounded-full bg-primary/60"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface Member {
  user_id: number
  display_name: string | null
  username: string | null
  has_photo: boolean
  message_count: number
  reaction_count: number
  first_seen_at: string | null
  last_active_at: string | null
  is_active: boolean
  in_chat?: boolean
}

function memberLabel(m: Member) { return m.display_name ?? m.username ?? String(m.user_id) }
function memberInitials(m: Member) { return (m.display_name ?? m.username ?? '#').slice(0, 2).toUpperCase() }
function memberPhotoUrl(m: Member) {
  if (!m.has_photo) return undefined
  return `${apiClient.defaults.baseURL}/users/${m.user_id}/photo`
}
function formatRelative(iso: string | null) {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

interface UserStats {
  user_id: number
  username: string | null
  display_name: string | null
  total: number
  reaction_count: number
  first_date: string | null
  last_date: string | null
  avg_per_day: number
  top_type: string | null
}

function MemberDrawer({ member, chatId, onClose }: { member: Member | null; chatId: number; onClose: () => void }) {
  const [stats, setStats] = useState<UserStats | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!member) { setStats(null); return }
    setLoading(true)
    apiClient.get<UserStats>('/stats/user-stats', { params: { chat_id: chatId, user_id: member.user_id } })
      .then((r) => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [member?.user_id, chatId])

  const m = member

  return (
    <Drawer open={!!m} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent className="max-h-[80vh] border-0">
        {m && (
          <>
            <div className="bg-gradient-to-b from-muted/60 to-background -mt-7 pt-7 px-4 pb-4 border-b border-border/50 rounded-t-[10px]">
              <div className="flex items-center gap-4">
                <Avatar className="size-14 ring-2 ring-border shadow-md">
                  <AvatarImage src={memberPhotoUrl(m)} />
                  <AvatarFallback className="text-lg font-bold">{memberInitials(m)}</AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-base truncate">{memberLabel(m)}</p>
                  {m.username && <p className="text-sm text-muted-foreground">@{m.username}</p>}
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant={m.is_active ? 'default' : 'secondary'} className="text-xs px-1.5 py-0">
                      {m.is_active ? 'active' : 'inactive'}
                    </Badge>
                    {m.in_chat === true && <Badge variant="outline" className="text-xs px-1.5 py-0">in chat</Badge>}
                    {m.in_chat === false && <Badge variant="outline" className="text-xs px-1.5 py-0 text-muted-foreground">left</Badge>}
                  </div>
                </div>
              </div>
            </div>
            <div className="overflow-y-auto px-4 py-3 space-y-1">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)
              ) : (
                <>
                  {[
                    ['Messages', m.message_count.toLocaleString()],
                    ['Reactions given', m.reaction_count > 0 ? m.reaction_count.toLocaleString() : '—'],
                    ['Avg / day', stats?.avg_per_day ?? '—'],
                    ['Top type', stats?.top_type ?? '—'],
                    ['First seen', stats?.first_date ? new Date(stats.first_date).toLocaleDateString() : '—'],
                    ['Last active', m.last_active_at ? new Date(m.last_active_at).toLocaleDateString() : '—'],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                      <span className="text-sm text-muted-foreground">{label}</span>
                      <span className="text-sm font-medium tabular-nums">{String(value)}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </>
        )}
      </DrawerContent>
    </Drawer>
  )
}

function MembersTab({ chatId }: { chatId: number }) {
  const [members, setMembers] = useState<Member[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [sessionAvailable, setSessionAvailable] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive' | 'in_chat' | 'left'>('all')
  const [selected, setSelected] = useState<Member | null>(null)
  const loaded = useRef(false)
  const sessionChecked = useRef(false)

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    setLoading(true)
    apiClient.get<Member[]>('/stats/members', { params: { chat_id: chatId } })
      .then((r) => setMembers(r.data))
      .catch(() => setMembers([]))
      .finally(() => setLoading(false))
  }, [chatId])

  useEffect(() => {
    if (sessionChecked.current) return
    sessionChecked.current = true
    apiClient.get<{ available: boolean }>('/threads/status')
      .then((r) => setSessionAvailable(r.data.available))
      .catch(() => setSessionAvailable(false))
  }, [])

  function handleSync() {
    setSyncing(true)
    apiClient.post<Member[]>('/stats/members/sync', null, { params: { chat_id: chatId } })
      .then((r) => setMembers(r.data))
      .catch(() => toast.error('Sync failed'))
      .finally(() => setSyncing(false))
  }

  const hasChatInfo = (members ?? []).some((m) => m.in_chat !== undefined)

  const filtered = (members ?? []).filter((m) => {
    if (filter === 'active' && !m.is_active) return false
    if (filter === 'inactive' && m.is_active) return false
    if (filter === 'in_chat' && m.in_chat !== true) return false
    if (filter === 'left' && m.in_chat !== false) return false
    if (!search) return true
    const q = search.toLowerCase()
    return (
      (m.display_name ?? '').toLowerCase().includes(q) ||
      (m.username ?? '').toLowerCase().includes(q) ||
      String(m.user_id).includes(q)
    )
  })

  const filters: { key: typeof filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'inactive', label: 'Inactive' },
    ...(hasChatInfo ? [
      { key: 'in_chat' as typeof filter, label: 'In chat' },
      { key: 'left' as typeof filter, label: 'Left' },
    ] : []),
  ]

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
          <div className="flex items-center justify-between gap-2">
            <div className="flex rounded-md border text-xs">
              {filters.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`h-7 px-2.5 transition-colors first:rounded-l-md last:rounded-r-md ${filter === f.key ? 'bg-muted font-semibold' : 'hover:bg-muted/50'}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            {members && (
              <p className="text-xs text-muted-foreground shrink-0">
                {filtered.length} / {members.length}
                {!sessionAvailable && <span className="ml-1 opacity-60">· senders only</span>}
              </p>
            )}
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
              <Item key={m.user_id} className="px-2 cursor-pointer" onClick={() => setSelected(m)}>
                <ItemMedia>
                  <Avatar className="h-9 w-9">
                    <AvatarImage src={memberPhotoUrl(m)} />
                    <AvatarFallback className="text-xs">{memberInitials(m)}</AvatarFallback>
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
                  <Badge variant={m.is_active ? 'default' : 'secondary'} className="text-xs px-1.5 py-0">
                    {m.is_active ? 'active' : 'inactive'}
                  </Badge>
                  {m.in_chat === false && (
                    <span className="text-[10px] text-muted-foreground">left</span>
                  )}
                </ItemActions>
              </Item>
            ))
          )}
        </CardContent>
      </Card>
      <MemberDrawer member={selected} chatId={chatId} onClose={() => setSelected(null)} />
    </>
  )
}

export default function StatsGroupPage() {
  const { t } = useTranslation()
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const numericChatId = Number(chatId)
  const { data: identity } = useGetIdentity<{ id: string; name: string; role: string }>()
  const isAdmin = identity?.role === 'admin' || identity?.role === 'owner'

  const PERIOD_KEY = 'stats_period'
  const savedPeriod = Number(localStorage.getItem(PERIOD_KEY) || 30) as Period

  const [groupTitle, setGroupTitle] = useState<string>('')
  const [data, setData] = useState<GroupData | null>(null)
  const [periodData, setPeriodData] = useState<PeriodData | null>(null)
  const [loading, setLoading] = useState(true)
  const [periodLoading, setPeriodLoading] = useState(false)
  const [period, setPeriodState] = useState<Period>([7, 30, 90, 0].includes(savedPeriod) ? savedPeriod : 30)
  const setPeriod = (v: Period) => {
    setPeriodState(v)
    localStorage.setItem(PERIOD_KEY, String(v))
  }

  useEffect(() => {
    if (!numericChatId) return
    setLoading(true)
    Promise.all([
      apiClient.get<StatsOverview>('/stats/overview', { params: { chat_id: numericChatId } }),
      apiClient.get<StatsGroup[]>('/stats/groups'),
    ])
      .then(([overviewRes, groupsRes]) => {
        const grp = groupsRes.data.find((g) => g.chat_id === numericChatId)
        setGroupTitle(grp?.title ?? `Group ${chatId}`)
        setData((prev) => prev ? { ...prev, overview: overviewRes.data } : {
          overview: overviewRes.data,
          topUsers: [], byHour: [], byDay: [], types: [], words: [], byMonth: [], mentions: [],
          avgLength: [], responseTime: null, mediaTrend: [],
        })
      })
      .catch(() => toast.error('Failed to load group stats'))
      .finally(() => setLoading(false))
  }, [numericChatId, chatId])

  useEffect(() => {
    if (!numericChatId) return
    setPeriodLoading(true)
    const p: Record<string, number> = { chat_id: numericChatId }
    if (period > 0) p.days = period

    Promise.all([
      apiClient.get<TopUser[]>('/stats/top-users', { params: { ...p, limit: 10 } }),
      apiClient.get<HourActivity[]>('/stats/activity-by-hour', { params: p }),
      apiClient.get<DayActivity[]>('/stats/activity-by-day', { params: p }),
      apiClient.get<MessageType[]>('/stats/message-types', { params: p }),
      apiClient.get<WordCount[]>('/stats/words', { params: { ...p, limit: 20 } }),
      apiClient.get<MonthActivity[]>('/stats/activity-by-month', { params: p }),
      apiClient.get<MentionStat[]>('/stats/mention-stats', { params: { ...p, limit: 15 } }),
      apiClient.get<DailyActivity[]>('/stats/daily-activity', { params: p }),
      apiClient.get<MemberEvent[]>('/stats/member-events', { params: p }),
      apiClient.get<AvgMessageLength[]>('/stats/avg-message-length', { params: { ...p, limit: 10 } }),
      apiClient.get<ResponseTimeData>('/stats/response-time', { params: { ...p, limit: 10 } }),
      apiClient.get<MediaTrend[]>('/stats/media-trend', { params: p }),
    ])
      .then(([usersRes, hourRes, dayRes, typesRes, wordsRes, monthRes, mentionRes, dailyRes, eventsRes, avgLenRes, rtRes, mtRes]) => {
        setData((prev) => ({
          overview: prev?.overview ?? { chat_id: numericChatId, total_messages: 0, unique_users: 0, first_date: null, last_date: null },
          topUsers: usersRes.data,
          byHour: hourRes.data,
          byDay: dayRes.data,
          types: typesRes.data,
          words: wordsRes.data,
          byMonth: monthRes.data,
          mentions: mentionRes.data,
          avgLength: avgLenRes.data,
          responseTime: rtRes.data,
          mediaTrend: mtRes.data,
        }))
        setPeriodData({ daily: dailyRes.data, memberEvents: eventsRes.data })
      })
      .catch(() => toast.error('Failed to load period stats'))
      .finally(() => setPeriodLoading(false))
  }, [numericChatId, period])

  const hourData = Array.from({ length: 24 }, (_, h) => {
    const found = data?.byHour.find((x) => x.hour === h)
    return { hour: `${h}:00`, count: found?.count ?? 0 }
  })

  const dayData = Array.from({ length: 7 }, (_, d) => {
    const found = data?.byDay.find((x) => x.day === d)
    return { day: DAY_NAMES[d], count: found?.count ?? 0 }
  })

  const hasMemberEvents = (periodData?.memberEvents.length ?? 0) > 0

  const typesWithPercent = data?.types.map((item) => {
    const total = data.types.reduce((s, tt) => s + tt.count, 0)
    return { ...item, percent: total > 0 ? ((item.count / total) * 100).toFixed(1) : '0' }
  }) ?? []

  const exportData = (format: 'json' | 'csv') => {
    if (!data) return
    const payload = {
      group: { chat_id: numericChatId, title: groupTitle },
      overview: data.overview, topUsers: data.topUsers,
      byHour: data.byHour, byDay: data.byDay, types: data.types,
      words: data.words, byMonth: data.byMonth, mentions: data.mentions,
      daily: periodData?.daily ?? [], memberEvents: periodData?.memberEvents ?? [],
    }
    let blob: Blob
    let filename: string
    if (format === 'json') {
      blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      filename = `yoink-stats-${numericChatId}.json`
    } else {
      const rows = data.topUsers.map((u) => [u.user_id, u.username ?? '', u.display_name ?? '', u.count])
      const csv = ['user_id,username,display_name,count', ...rows.map((r) => r.join(','))].join('\n')
      blob = new Blob([csv], { type: 'text/csv' })
      filename = `yoink-stats-${numericChatId}.csv`
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  const isLoading = loading || !data
  const isPeriodLoading = periodLoading || !periodData

  const peakHour = data && data.byHour.length > 0
    ? `${data.byHour.reduce((a, b) => b.count > a.count ? b : a).hour}:00`
    : '-'

  const peakDay = data && data.byDay.length > 0
    ? DAY_NAMES[data.byDay.reduce((a, b) => b.count > a.count ? b : a).day] ?? '-'
    : '-'

  const avgPerDay = (() => {
    if (periodData?.daily && periodData.daily.length > 0) {
      const total = periodData.daily.reduce((s, d) => s + d.messages, 0)
      return Math.round(total / periodData.daily.length)
    }
    if (!data?.overview.first_date || !data?.overview.last_date) return '-'
    const days = Math.max(1, Math.ceil(
      (new Date(data.overview.last_date).getTime() - new Date(data.overview.first_date).getTime()) / 86_400_000
    ))
    return Math.round(data.overview.total_messages / days)
  })()

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => navigate('/stats')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold truncate">
            {loading ? <Skeleton className="h-5 w-40 inline-block" /> : groupTitle}
          </h1>
          {!isLoading && (
            <p className="text-xs text-muted-foreground">
              {t('stats.total_messages')}: {data.overview.total_messages.toLocaleString()}
              {' · '}
              {t('stats.unique_users')}: {data.overview.unique_users.toLocaleString()}
            </p>
          )}
        </div>
        {data && (
          <div className="flex gap-1 shrink-0">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => exportData('json')}>
              <Download className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      <Tabs defaultValue="stats">
        <div className="flex items-center justify-between gap-2">
          <TabsList>
            <TabsTrigger value="stats">{t('stats.tab_stats')}</TabsTrigger>
            {isAdmin && <TabsTrigger value="members">{t('stats.tab_members', { defaultValue: 'Members' })}</TabsTrigger>}
            {identity?.role === 'owner' && <TabsTrigger value="import">{t('stats.tab_import')}</TabsTrigger>}
          </TabsList>
          <PeriodToggle value={period} onChange={setPeriod} />
        </div>

        <TabsContent value="stats" className="space-y-4 mt-4">
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-2">
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => <StatCardSkeleton key={i} />)
            ) : (
              <>
                <StatCard label={t('stats.total_messages')} value={data.overview.total_messages} icon={<MessageSquare className="h-3.5 w-3.5" />} />
                <StatCard label={t('stats.unique_users')} value={data.overview.unique_users} icon={<UsersIcon className="h-3.5 w-3.5" />} />
                <StatCard label="Since" value={formatDate(data.overview.first_date)} icon={<Calendar className="h-3.5 w-3.5" />} />
                <StatCard label="Avg / day" value={avgPerDay} />
                <StatCard label="Peak hour" value={peakHour} />
                <StatCard label="Peak day" value={peakDay} />
              </>
            )}
          </div>

          {/* Daily activity chart */}
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle className="text-sm font-medium">{t('stats.message_history')}</CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-3">
              {isPeriodLoading ? (
                <Skeleton className="h-44 w-full" />
              ) : (periodData?.daily.length ?? 0) === 0 ? (
                <div className="flex h-44 items-center justify-center text-sm text-muted-foreground">No data</div>
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={periodData!.daily} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v: string) => v.slice(5)} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                    <Tooltip labelFormatter={(v) => `Date: ${v}`} formatter={(v, name) => [v, name === 'messages' ? 'Messages' : 'Active users']} />
                    <Legend formatter={(v) => v === 'messages' ? 'Messages' : 'Active users'} wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="messages" stroke={chartColors()[0]} dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="dau" stroke={chartColors()[3]} dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Member events */}
          {(hasMemberEvents || isPeriodLoading) && (
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">Member events</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-36 w-full" />
                ) : (
                  <ResponsiveContainer width="100%" height={140}>
                    <BarChart data={periodData!.memberEvents} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v: string) => v.slice(5)} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                      <Tooltip labelFormatter={(v) => `Date: ${v}`} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="joined" fill={chartColors()[3]} radius={[2, 2, 0, 0]} stackId="e" />
                      <Bar dataKey="left" fill={chartColors()[2]} radius={[2, 2, 0, 0]} stackId="e" />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          )}

          {/* Top users + Message types */}
          <div className="grid gap-3 md:grid-cols-5">
            <Card className="md:col-span-3">
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.top_users')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                {isPeriodLoading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <Skeleton className="size-7 rounded-full shrink-0" />
                        <Skeleton className="h-3.5 flex-1" />
                        <Skeleton className="h-3.5 w-10" />
                      </div>
                    ))}
                  </div>
                ) : (data?.topUsers.length ?? 0) === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">No data</p>
                ) : (
                  <div className="space-y-1">
                    {data!.topUsers.map((u, i) => {
                      const max = data!.topUsers[0]?.count ?? 1
                      const pct = max > 0 ? (u.count / max) * 100 : 0
                      return (
                        <div
                          key={u.user_id}
                          className="flex items-center gap-2.5 py-1.5 cursor-pointer rounded-md px-1 -mx-1 hover:bg-muted/50 transition-colors"
                          onClick={() => navigate(`/stats/${numericChatId}/user/${u.user_id}?group=${encodeURIComponent(groupTitle)}`)}
                        >
                          <Avatar className="size-7 shrink-0">
                            <AvatarImage src={userPhotoUrl(u)} />
                            <AvatarFallback
                              className="text-[10px] font-bold"
                              style={{ backgroundColor: `${chartColors()[i % chartColors().length]}20`, color: chartColors()[i % chartColors().length] }}
                            >
                              {userInitials(u)}
                            </AvatarFallback>
                          </Avatar>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-sm font-medium truncate">{userLabel(u)}</span>
                              <span className="text-xs tabular-nums text-muted-foreground shrink-0">{u.count.toLocaleString()}</span>
                            </div>
                            <div className="h-1 rounded-full bg-muted mt-1">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{ width: `${pct}%`, backgroundColor: chartColors()[i % chartColors().length] }}
                              />
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.message_types')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-40 w-full" />
                ) : typesWithPercent.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">No data</p>
                ) : (
                  <div className="space-y-3">
                    <ResponsiveContainer width="100%" height={130}>
                      <PieChart>
                        <Pie
                          data={typesWithPercent}
                          dataKey="count"
                          nameKey="type"
                          cx="50%" cy="50%"
                          innerRadius={30} outerRadius={55}
                          paddingAngle={1} label={false}
                        >
                          {typesWithPercent.map((_, i) => (
                            <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v, name) => [Number(v).toLocaleString(), name]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="space-y-1">
                      {typesWithPercent.map((item, i) => (
                        <div key={item.type} className="flex items-center gap-2 text-xs">
                          <span className="inline-block h-2 w-2 rounded-sm shrink-0" style={{ backgroundColor: chartColors()[i % chartColors().length] }} />
                          <span className="text-muted-foreground flex-1 truncate">{item.type}</span>
                          <span className="tabular-nums font-medium">{Number(item.count).toLocaleString()}</span>
                          <span className="tabular-nums text-muted-foreground w-9 text-right">{item.percent}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Activity by Hour & Day */}
          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.activity_by_hour')}</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-36 w-full" />
                ) : (
                  <ResponsiveContainer width="100%" height={140}>
                    <BarChart data={hourData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="hour" tick={{ fontSize: 8 }} interval={3} />
                      <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                      <Tooltip formatter={(v) => [v, 'Messages']} />
                      <Bar dataKey="count" fill={chartColors()[1]} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.activity_by_day')}</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-36 w-full" />
                ) : (
                  <ResponsiveContainer width="100%" height={140}>
                    <BarChart data={dayData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="day" tick={{ fontSize: 9 }} />
                      <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                      <Tooltip formatter={(v) => [v, 'Messages']} />
                      <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                        {dayData.map((_, i) => (
                          <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Monthly activity */}
          {(!isPeriodLoading && (data?.byMonth.length ?? 0) > 0) && (
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.activity_by_month')}</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3">
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart
                    data={data!.byMonth.map((m) => ({ month: formatMonthLabel(m.month), count: m.count }))}
                    margin={{ top: 4, right: 8, left: -16, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                    <Tooltip formatter={(v) => [v, 'Messages']} />
                    <Bar dataKey="count" fill={chartColors()[2]} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Words + Mentions */}
          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.top_words')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-48 w-full" />
                ) : (
                  <RankedList items={data?.words ?? []} labelKey="word" valueKey="count" limit={15} />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">{t('stats.top_mentions')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                {isPeriodLoading ? (
                  <Skeleton className="h-48 w-full" />
                ) : (
                  <RankedList items={data?.mentions ?? []} labelKey="mention" valueKey="count" limit={15} />
                )}
              </CardContent>
            </Card>
          </div>

          {/* Response time */}
          {!isPeriodLoading && data?.responseTime && data.responseTime.total_replies > 0 && (
            <Card>
              <CardHeader className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                    Response time
                  </CardTitle>
                  <div className="flex gap-3 text-xs text-muted-foreground">
                    <span>avg <span className="font-medium text-foreground">{data.responseTime.overall_avg}</span></span>
                    <span>median <span className="font-medium text-foreground">{data.responseTime.overall_median}</span></span>
                    <span className="tabular-nums">{data.responseTime.total_replies.toLocaleString()} replies</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <div className="divide-y divide-border rounded-md border">
                  {data.responseTime.users.map((u) => (
                    <div key={u.user_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                      <span className="font-medium truncate flex-1">{u.display_name ?? u.username ?? String(u.user_id)}</span>
                      <span className="text-xs text-muted-foreground tabular-nums">{u.reply_count} replies</span>
                      <span className="text-xs tabular-nums w-12 text-right">{u.median}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Avg message length */}
          {!isPeriodLoading && (data?.avgLength.length ?? 0) > 0 && (
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Type className="h-3.5 w-3.5 text-muted-foreground" />
                  Message length by user
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <div className="divide-y divide-border rounded-md border">
                  {data!.avgLength.map((u) => (
                    <div key={u.user_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                      <span className="font-medium truncate flex-1">{u.display_name ?? u.username ?? String(u.user_id)}</span>
                      <span className="text-xs text-muted-foreground tabular-nums">{u.total.toLocaleString()} msgs</span>
                      <span className="text-xs tabular-nums">avg <span className="font-medium">{u.avg_len}</span></span>
                      <span className="text-xs tabular-nums text-muted-foreground">max {u.max_len}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Media vs Text trend */}
          {!isPeriodLoading && (data?.mediaTrend.length ?? 0) > 1 && (
            <Card>
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-sm font-medium">Media vs Text trend</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3">
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart
                    data={data!.mediaTrend.map((m) => ({ month: formatMonthLabel(m.month), text: m.text, media: m.media }))}
                    margin={{ top: 4, right: 8, left: -16, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Area type="monotone" dataKey="text" stackId="1" stroke={chartColors()[0]} fill={chartColors()[0]} fillOpacity={0.4} />
                    <Area type="monotone" dataKey="media" stackId="1" stroke={chartColors()[4]} fill={chartColors()[4]} fillOpacity={0.4} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {isAdmin && (
          <TabsContent value="members" className="mt-4">
            <MembersTab chatId={numericChatId} />
          </TabsContent>
        )}
        <TabsContent value="import" className="mt-4">
          <ImportPage defaultChatId={String(numericChatId)} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
