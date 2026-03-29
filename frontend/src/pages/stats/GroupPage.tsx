import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { useGetIdentity } from '@refinedev/core'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@ui'
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

import { ArrowLeft, Calendar, Clock, Download, MessageSquare, Type, Users as UsersIcon } from 'lucide-react'

import { statsApi, type TopReactions } from '@stats/api'
import { threadsApi } from '@core/lib/api'
import { formatDateMonth } from '@core/lib/utils'
import { userInitials, userPhotoUrl } from '@core/lib/user-utils'
import type { DrawerUser } from '@stats/types'
import { Avatar, AvatarFallback, AvatarImage, Button, Card, CardContent, CardHeader, CardTitle, Skeleton } from '@ui'
import { toast } from '@core/components/ui/toast'
import { chartColors, PeriodToggle, StatCard, StatCardSkeleton } from '@core/components/charts'
import type { Period } from '@core/components/charts'
import type {
  DayActivity,
  HourActivity,
  Member,
  MentionStat,
  MessageType,
  MonthActivity,
  StatsOverview,
  TopUser,
  WordCount,
  AvgMessageLength,
  ResponseTimeData,
  MediaTrend,
} from '@stats/types'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


function userLabel(u: TopUser): string {
  return u.display_name ?? u.username ?? String(u.user_id)
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
  topReactions: TopReactions | null
}

interface PeriodData {
  daily: DailyActivity[]
  memberEvents: MemberEvent[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function RankedList<T extends object>({ items, labelKey, valueKey, limit = 10 }: {
  items: T[]
  labelKey: keyof T
  valueKey: keyof T
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


import { MembersTab, UserStatsDrawer } from './components'

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
  const [activeTab, setActiveTab] = useState('stats')
  const [members, setMembers] = useState<Member[] | null>(null)
  const [membersLoading, setMembersLoading] = useState(false)
  const [sessionAvailable, setSessionAvailable] = useState(false)
  const [chatAdmins, setChatAdmins] = useState<{ user_id: number; status: string }[]>([])
  const [selectedUser, setSelectedUser] = useState<DrawerUser | null>(null)
  const sessionChecked = useRef(false)
  const [period, setPeriodState] = useState<Period>([7, 30, 90, 0].includes(savedPeriod) ? savedPeriod : 30)
  const setPeriod = (v: Period) => {
    setPeriodState(v)
    localStorage.setItem(PERIOD_KEY, String(v))
  }

  useEffect(() => {
    if (!numericChatId) return
    statsApi.getChatAdmins(numericChatId)
      .then((r) => setChatAdmins(r.data))
      .catch(() => {})
  }, [numericChatId])

  useEffect(() => {
    if (!numericChatId) return
    setLoading(true)
    Promise.all([
      statsApi.getOverview({ chat_id: numericChatId }),
      statsApi.getGroups(),
    ])
      .then(([overviewRes, groupsRes]) => {
        const grp = groupsRes.data.find((g) => g.chat_id === numericChatId)
        setGroupTitle(grp?.title ?? `Group ${chatId}`)
        setData((prev) => prev ? { ...prev, overview: overviewRes.data } : {
          overview: overviewRes.data,
          topUsers: [], byHour: [], byDay: [], types: [], words: [], byMonth: [], mentions: [],
          avgLength: [], responseTime: null, mediaTrend: [], topReactions: null,
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
      statsApi.getTopUsers({ ...p, limit: 10 }),
      statsApi.getActivityByHour(p),
      statsApi.getActivityByDay(p),
      statsApi.getMessageTypes(p),
      statsApi.getWords({ ...p, limit: 20 }),
      statsApi.getActivityByMonth(p),
      statsApi.getMentions({ ...p, limit: 15 }),
      statsApi.getDailyActivity(p),
      statsApi.getMemberEvents(p),
      statsApi.getAvgMessageLength({ ...p, limit: 10 }),
      statsApi.getResponseTime({ ...p, limit: 10 }),
      statsApi.getMediaTrend(p),
      isAdmin ? statsApi.getTopReactions({ ...p, limit: 10 }).catch(() => null) : Promise.resolve(null),
    ])
      .then(([usersRes, hourRes, dayRes, typesRes, wordsRes, monthRes, mentionRes, dailyRes, eventsRes, avgLenRes, rtRes, mtRes, reactRes]) => {
        setData((prev) => ({
          overview: prev?.overview ?? { chat_id: numericChatId, total_messages: 0, unique_users: 0, total_reactions: 0, first_date: null, last_date: null },
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
          topReactions: reactRes ? reactRes.data : null,
        }))
        setPeriodData({ daily: dailyRes.data as DailyActivity[], memberEvents: eventsRes.data as MemberEvent[] })
      })
      .catch(() => toast.error('Failed to load period stats'))
      .finally(() => setPeriodLoading(false))
  }, [numericChatId, period])

  const isChatAdminResolved = identity !== undefined
  useEffect(() => {
    if (!isChatAdminResolved || !numericChatId) return
    const canAccess = isAdmin || chatAdmins.some((a) => a.user_id === Number(identity?.id))
    if (!canAccess) return
    setMembersLoading(true)
    const params: Record<string, unknown> = { chat_id: numericChatId }
    if (period > 0) params.days = period
    statsApi.getMembers({ chat_id: numericChatId })
      .then((r) => setMembers(r.data))
      .catch(() => setMembers([]))
      .finally(() => setMembersLoading(false))
  }, [isChatAdminResolved, isAdmin, numericChatId, period, chatAdmins])

  useEffect(() => {
    if (!isAdmin || sessionChecked.current) return
    sessionChecked.current = true
    threadsApi.getStatus()
      .then((r) => setSessionAvailable(r.data.available))
      .catch(() => setSessionAvailable(false))
  }, [isAdmin])

  const isChatAdmin = isAdmin || chatAdmins.some((a) => a.user_id === Number(identity?.id))

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

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center justify-between gap-2">
          <TabsList>
            <TabsTrigger value="stats">{t('stats.tab_stats')}</TabsTrigger>
            {isChatAdmin && <TabsTrigger value="members">{t('stats.tab_members', { defaultValue: 'Members' })}</TabsTrigger>}
            {identity?.role === 'owner' && <TabsTrigger value="import">{t('stats.tab_import')}</TabsTrigger>}
          </TabsList>
          {activeTab !== 'import' && <PeriodToggle value={period} onChange={setPeriod} />}
        </div>

        <TabsContent value="stats" className="space-y-4 mt-4">
          {/* KPIs */}
          {isLoading ? (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                {Array.from({ length: 3 }).map((_, i) => <StatCardSkeleton key={i} />)}
              </div>
              <div className="grid grid-cols-4 gap-2">
                {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <StatCard label={t('stats.total_messages')} value={data.overview.total_messages} icon={<MessageSquare className="h-3.5 w-3.5" />} />
                <StatCard label={t('stats.unique_users')} value={data.overview.unique_users} icon={<UsersIcon className="h-3.5 w-3.5" />} />
                <StatCard label="Since" value={formatDateMonth(data.overview.first_date)} icon={<Calendar className="h-3.5 w-3.5" />} />
              </div>
              <div className={`grid gap-2 ${isAdmin && data.overview.total_reactions > 0 ? 'grid-cols-4' : 'grid-cols-3'}`}>
                <StatCard label="Avg / day" value={avgPerDay} compact />
                <StatCard label="Peak hour" value={peakHour} compact />
                <StatCard label="Peak day" value={peakDay} compact />
                {isAdmin && data.overview.total_reactions > 0 && (
                  <StatCard label="Reactions" value={data.overview.total_reactions} compact />
                )}
              </div>
            </div>
          )}

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
                          onClick={() => setSelectedUser({ user_id: u.user_id, username: u.username, display_name: u.display_name })}
                        >
                          <Avatar className="size-7 shrink-0">
                            <AvatarImage src={userPhotoUrl(u.user_id)} />
                            <AvatarFallback
                              className="text-[10px] font-bold"
                              style={{ backgroundColor: `${chartColors()[i % chartColors().length]}20`, color: chartColors()[i % chartColors().length] }}
                            >
                              {userInitials({ first_name: u.display_name, username: u.username })}
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

          {isAdmin && data?.topReactions && (data.topReactions.top_givers.length > 0 || data.topReactions.top_emoji.length > 0) && (
            <div className="grid grid-cols-2 gap-3">
              {data.topReactions.top_givers.length > 0 && (
                <Card>
                  <CardHeader className="px-4 py-3">
                    <CardTitle className="text-sm">Top reaction givers</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    <RankedList items={data.topReactions.top_givers.map(u => ({ label: u.display_name ?? u.username ?? String(u.user_id), value: u.reaction_count ?? u.count }))} labelKey="label" valueKey="value" />
                  </CardContent>
                </Card>
              )}
              {data.topReactions.top_emoji.length > 0 && (
                <Card>
                  <CardHeader className="px-4 py-3">
                    <CardTitle className="text-sm">Top emoji</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    <RankedList items={data.topReactions.top_emoji.map(e => ({ label: e.reaction_type === 'emoji' ? (e.reaction_key ?? e.emoji ?? '') : `[custom]`, value: e.count }))} labelKey="label" valueKey="value" />
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        {isChatAdmin && (
          <TabsContent value="members" className="mt-4">
            <MembersTab
              chatId={numericChatId}
              members={members}
              loading={membersLoading}
              onLoad={setMembers}
              sessionAvailable={sessionAvailable && isAdmin}
              period={period}
            />
          </TabsContent>
        )}
        <TabsContent value="import" className="mt-4">
          <ImportPage defaultChatId={String(numericChatId)} />
        </TabsContent>
      </Tabs>

      <UserStatsDrawer user={selectedUser} chatId={numericChatId} onClose={() => setSelectedUser(null)} />
    </div>
  )
}
