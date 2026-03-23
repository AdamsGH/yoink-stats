import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import {
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

import { Download } from 'lucide-react'

import { apiClient } from '@core/lib/api-client'
import { cn } from '@core/lib/utils'
import { Button } from '@core/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@core/components/ui/card'
import { Skeleton } from '@core/components/ui/skeleton'
import { toast } from '@core/components/ui/toast'
import type {
  DailyHistory,
  DayActivity,
  HourActivity,
  MentionStat,
  MessageType,
  MonthActivity,
  StatsGroup,
  StatsOverview,
  TopUser,
  WordCount,
} from '@stats/types'

const CTP_FALLBACKS = [
  '#8aadf4', '#c6a0f6', '#ed8796', '#a6da95', '#f5a97f',
  '#91d7e3', '#eed49f', '#f5bde6', '#8bd5ca', '#b7bdf8',
]
const CTP_VARS = [
  '--ctp-blue', '--ctp-mauve', '--ctp-red', '--ctp-green', '--ctp-peach',
  '--ctp-sky', '--ctp-yellow', '--ctp-pink', '--ctp-teal', '--ctp-lavender',
]

let _chartColors: string[] | null = null
function chartColors(): string[] {
  if (_chartColors) return _chartColors
  const style = getComputedStyle(document.documentElement)
  _chartColors = CTP_VARS.map((name, i) => style.getPropertyValue(name).trim() || CTP_FALLBACKS[i])
  return _chartColors
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const PERIOD_OPTIONS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
  { label: 'All', value: 0 },
] as const

type Period = (typeof PERIOD_OPTIONS)[number]['value']

function PeriodToggle({ value, onChange }: { value: Period; onChange: (v: Period) => void }) {
  return (
    <div className="flex rounded-md border">
      {PERIOD_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          variant="ghost"
          size="sm"
          onClick={() => onChange(opt.value)}
          className={cn(
            'h-7 rounded-none px-2.5 text-xs first:rounded-l-md last:rounded-r-md',
            value === opt.value && 'bg-muted font-semibold',
          )}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string | number | null }) {
  const display = value === null ? '-' : typeof value === 'number' ? value.toLocaleString() : value
  const isLong = typeof display === 'string' && display.length > 8
  return (
    <Card className="select-none overflow-hidden">
      <CardContent className="pt-4 pb-3">
        <div className={`font-bold tabular-nums text-primary truncate ${isLong ? 'text-base' : 'text-2xl'}`}>
          {display}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  )
}

function StatCardSkeleton() {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 space-y-2">
        <Skeleton className="h-7 w-20" />
        <Skeleton className="h-3 w-28" />
      </CardContent>
    </Card>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
  })
}

function userLabel(u: TopUser): string {
  return u.display_name ?? u.username ?? String(u.user_id)
}

/** Estimate YAxis label width: ~7px per char, min 48, max 40% of viewport. */
function yAxisWidth(labels: string[]): number {
  const maxLen = labels.reduce((m, l) => Math.max(m, l.length), 0)
  const maxAllowed = Math.floor((typeof window !== 'undefined' ? window.innerWidth : 400) * 0.4)
  return Math.min(maxAllowed, Math.max(48, maxLen * 7))
}

function formatMonthLabel(month: string): string {
  const [year, mon] = month.split('-')
  const date = new Date(Number(year), Number(mon) - 1, 1)
  return date.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function computeDerivedStats(
  overview: StatsOverview,
  byHour: HourActivity[],
  byDay: DayActivity[],
): { avgPerDay: number; peakHour: string; peakDay: string } {
  let avgPerDay = 0
  if (overview.first_date && overview.last_date) {
    const start = new Date(overview.first_date).getTime()
    const end = new Date(overview.last_date).getTime()
    const days = Math.max(1, Math.ceil((end - start) / 86_400_000))
    avgPerDay = Math.round(overview.total_messages / days)
  }

  let peakHour = '-'
  if (byHour.length > 0) {
    const max = byHour.reduce((a, b) => (b.count > a.count ? b : a))
    peakHour = `${max.hour}:00`
  }

  let peakDay = '-'
  if (byDay.length > 0) {
    const max = byDay.reduce((a, b) => (b.count > a.count ? b : a))
    peakDay = DAY_NAMES[max.day] ?? '-'
  }

  return { avgPerDay, peakHour, peakDay }
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
}

export default function StatsGroupPage() {
  const { t } = useTranslation()
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const numericChatId = Number(chatId)

  const [groupTitle, setGroupTitle] = useState<string>('')
  const [data, setData] = useState<GroupData | null>(null)
  const [history, setHistory] = useState<DailyHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [period, setPeriod] = useState<Period>(30)

  useEffect(() => {
    if (!numericChatId) return
    setLoading(true)

    Promise.all([
      apiClient.get<StatsOverview>('/stats/overview', { params: { chat_id: numericChatId } }),
      apiClient.get<TopUser[]>('/stats/top-users', { params: { chat_id: numericChatId, limit: 10 } }),
      apiClient.get<HourActivity[]>('/stats/activity-by-hour', { params: { chat_id: numericChatId } }),
      apiClient.get<DayActivity[]>('/stats/activity-by-day', { params: { chat_id: numericChatId } }),
      apiClient.get<MessageType[]>('/stats/message-types', { params: { chat_id: numericChatId } }),
      apiClient.get<WordCount[]>('/stats/words', { params: { chat_id: numericChatId, limit: 20 } }),
      apiClient.get<StatsGroup[]>('/stats/groups'),
      apiClient.get<MonthActivity[]>('/stats/activity-by-month', { params: { chat_id: numericChatId } }),
      apiClient.get<MentionStat[]>('/stats/mention-stats', { params: { chat_id: numericChatId, limit: 15 } }),
    ])
      .then(([overviewRes, usersRes, hourRes, dayRes, typesRes, wordsRes, groupsRes, monthRes, mentionRes]) => {
        setData({
          overview: overviewRes.data,
          topUsers: usersRes.data,
          byHour: hourRes.data,
          byDay: dayRes.data,
          types: typesRes.data,
          words: wordsRes.data,
          byMonth: monthRes.data,
          mentions: mentionRes.data,
        })
        const grp = groupsRes.data.find((g) => g.chat_id === numericChatId)
        setGroupTitle(grp?.title ?? `Group ${chatId}`)
      })
      .catch(() => toast.error('Failed to load group stats'))
      .finally(() => setLoading(false))
  }, [numericChatId, chatId])

  useEffect(() => {
    if (!numericChatId) return
    setHistoryLoading(true)
    const params: Record<string, number> = { chat_id: numericChatId }
    if (period > 0) params.days = period
    apiClient
      .get<DailyHistory[]>('/stats/history', { params })
      .then((res) => setHistory(res.data))
      .catch(() => toast.error('Failed to load message history'))
      .finally(() => setHistoryLoading(false))
  }, [numericChatId, period])

  const hourData = Array.from({ length: 24 }, (_, h) => {
    const found = data?.byHour.find((x) => x.hour === h)
    return { hour: `${h}:00`, count: found?.count ?? 0 }
  })

  const dayData = Array.from({ length: 7 }, (_, d) => {
    const found = data?.byDay.find((x) => x.day === d)
    return { day: DAY_NAMES[d], count: found?.count ?? 0 }
  })

  const derived = data ? computeDerivedStats(data.overview, data.byHour, data.byDay) : null

  const exportData = (format: 'json' | 'csv') => {
    if (!data) return
    const payload = {
      group: { chat_id: numericChatId, title: groupTitle },
      overview: data.overview,
      topUsers: data.topUsers,
      byHour: data.byHour,
      byDay: data.byDay,
      types: data.types,
      words: data.words,
      byMonth: data.byMonth,
      mentions: data.mentions,
      history,
    }
    let blob: Blob
    let filename: string
    if (format === 'json') {
      blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      filename = `yoink-stats-${numericChatId}.json`
    } else {
      const rows = data.topUsers.map((u) => [
        u.user_id, u.username ?? '', u.display_name ?? '', u.count,
      ])
      const csv = ['user_id,username,display_name,count', ...rows.map((r) => r.join(','))].join('\n')
      blob = new Blob([csv], { type: 'text/csv' })
      filename = `yoink-stats-${numericChatId}.csv`
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const typesWithPercent = data?.types.map((item) => {
    const total = data.types.reduce((s, t) => s + t.count, 0)
    return { ...item, percent: total > 0 ? ((item.count / total) * 100).toFixed(1) : '0' }
  }) ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/stats')}>
          ← Back
        </Button>
        <h1 className="text-2xl font-bold">{loading ? <Skeleton className="h-7 w-48" /> : groupTitle}</h1>
        {data && (
          <div className="ml-auto flex gap-1">
            <Button variant="outline" size="sm" onClick={() => exportData('json')}>
              <Download className="mr-1 h-3.5 w-3.5" /> JSON
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportData('csv')}>
              <Download className="mr-1 h-3.5 w-3.5" /> CSV
            </Button>
          </div>
        )}
      </div>

      {/* Overview KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {loading || !data ? (
          Array.from({ length: 6 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard label={t('stats.total_messages')} value={data.overview.total_messages} />
            <StatCard label={t('stats.unique_users')} value={data.overview.unique_users} />
            <StatCard label="Avg / day" value={derived?.avgPerDay ?? '-'} />
            <StatCard label="Peak hour" value={derived?.peakHour ?? '-'} />
            <StatCard label="Peak day" value={derived?.peakDay ?? '-'} />
            <StatCard label="Active since" value={formatDate(data.overview.first_date)} />
          </>
        )}
      </div>

      {/* Message History */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">{t('stats.message_history')}</CardTitle>
          <PeriodToggle value={period} onChange={setPeriod} />
        </CardHeader>
        <CardContent>
          {historyLoading || loading ? (
            <Skeleton className="h-48 w-full" />
          ) : history.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
              No data
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={history} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip labelFormatter={(v) => `Date: ${v}`} formatter={(v) => [v, 'Messages']} />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke={chartColors()[0]}
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Top Users + Message Types side by side */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.top_users')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-48 w-full" />
            ) : data.topUsers.length === 0 ? (
              <div className="text-sm text-muted-foreground">No data</div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={Math.max(180, data.topUsers.length * 28)}>
                  <BarChart
                    data={data.topUsers.map((u) => ({ name: userLabel(u), count: u.count, userId: u.user_id }))}
                    layout="vertical"
                    margin={{ top: 0, right: 12, left: 4, bottom: 0 }}
                    onClick={(state) => {
                      if (state?.activePayload?.[0]?.payload?.userId) {
                        navigate(`/stats/${numericChatId}/user/${state.activePayload[0].payload.userId}?group=${encodeURIComponent(groupTitle)}`)
                      }
                    }}
                    className="cursor-pointer"
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
                    <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" width={yAxisWidth(data.topUsers.map(userLabel))} tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v) => [v, 'Messages']} />
                    <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                      {data.topUsers.map((_, i) => (
                        <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-1 text-xs text-muted-foreground text-center">Click a bar to view user details</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.message_types')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-52 w-full" />
            ) : typesWithPercent.length === 0 ? (
              <div className="text-sm text-muted-foreground">No data</div>
            ) : (
              <div className="space-y-3">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie
                      data={typesWithPercent}
                      dataKey="count"
                      nameKey="type"
                      cx="50%"
                      cy="50%"
                      innerRadius={35}
                      outerRadius={70}
                      paddingAngle={1}
                      label={false}
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
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-sm flex-shrink-0"
                        style={{ backgroundColor: chartColors()[i % chartColors().length] }}
                      />
                      <span className="text-muted-foreground flex-1 truncate">{item.type}</span>
                      <span className="tabular-nums font-medium">{Number(item.count).toLocaleString()}</span>
                      <span className="tabular-nums text-muted-foreground w-10 text-right">{item.percent}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Activity by Hour & Day */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.activity_by_hour')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-44 w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={hourData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="hour" tick={{ fontSize: 9 }} interval={3} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip formatter={(v) => [v, 'Messages']} />
                  <Bar dataKey="count" fill={chartColors()[1]} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.activity_by_day')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-44 w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={dayData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip formatter={(v) => [v, 'Messages']} />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
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

      {/* Activity by Month */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('stats.activity_by_month')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loading || !data ? (
            <Skeleton className="h-48 w-full" />
          ) : data.byMonth.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
              No data
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={data.byMonth.map((m) => ({ month: formatMonthLabel(m.month), count: m.count }))}
                margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip formatter={(v) => [v, 'Messages']} />
                <Bar dataKey="count" fill={chartColors()[2]} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Words + Mentions side by side */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.top_words')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-64 w-full" />
            ) : data.words.length === 0 ? (
              <div className="text-sm text-muted-foreground">No data</div>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, data.words.length * 22)}>
                <BarChart
                  data={data.words}
                  layout="vertical"
                  margin={{ top: 0, right: 12, left: 4, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
                  <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="word" width={yAxisWidth(data.words.map((w) => w.word))} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => [v, 'Occurrences']} />
                  <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                    {data.words.map((_, i) => (
                      <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stats.top_mentions')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-64 w-full" />
            ) : data.mentions.length === 0 ? (
              <div className="text-sm text-muted-foreground">No data</div>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, data.mentions.length * 22)}>
                <BarChart
                  data={data.mentions}
                  layout="vertical"
                  margin={{ top: 0, right: 12, left: 4, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
                  <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="mention" width={yAxisWidth(data.mentions.map((m) => m.mention))} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => [v, 'Mentions']} />
                  <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                    {data.mentions.map((_, i) => (
                      <Cell key={i} fill={chartColors()[i % chartColors().length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
