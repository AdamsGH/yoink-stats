import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Download, Film, Music, Package, Brain,
  Mic2, BarChart3, FileText, MessageCircle,
  CalendarDays, Clock, Hash,
} from 'lucide-react'
import {
  Bar, BarChart, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import { meApi, type DlOverview, type InsightStats, type MusicStats } from '@stats/api/me'
import { Card, CardContent, CardHeader, CardTitle, Skeleton } from '@ui'
import { toast } from '@core/components/ui/toast'
import type { UserStats } from '@core/types/plugin'
import { chartColors, StatCard, StatCardSkeleton } from '@core/components/charts'



// reusable components

function ChartSkeleton({ height = 120 }: { height?: number }) {
  return <Skeleton className="w-full rounded-md" style={{ height }} />
}

function SectionSkeleton({ stats = 3, chart = true }: { stats?: number; chart?: boolean }) {
  return (
    <div className="space-y-4">
      <div className={`grid grid-cols-${stats} gap-2`}>
        {Array.from({ length: stats }).map((_, i) => <StatCardSkeleton key={i} />)}
      </div>
      {chart && <ChartSkeleton />}
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground py-4 text-center">{text}</p>
}

function formatDayLabel(date: string) {
  const d = new Date(date)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function MiniBarChart({ data, dataKey = 'count', color, height = 120 }: {
  data: Array<Record<string, unknown>>
  dataKey?: string
  color: string
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 2, right: 2, left: -28, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="date" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v) => [v, '']}
        />
        <Bar dataKey={dataKey} fill={color} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function HorizontalBars({ data, nameKey, valueKey, colors }: {
  data: Array<Record<string, unknown>>
  nameKey: string
  valueKey: string
  colors: string[]
}) {
  if (!data.length) return null
  const max = Math.max(...data.map(d => Number(d[valueKey])))
  return (
    <div className="space-y-1.5">
      {data.map((d, i) => {
        const pct = Math.round((Number(d[valueKey]) / max) * 100)
        return (
          <div key={String(d[nameKey])} className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground w-4 tabular-nums shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between mb-0.5">
                <span className="truncate">{String(d[nameKey])}</span>
                <span className="tabular-nums font-medium ml-2 shrink-0">{Number(d[valueKey])}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted-foreground/20">
                <div
                  className="h-1.5 rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: colors[i % colors.length] }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const PLATFORM_LABELS: Record<string, string> = {
  spotify: 'Spotify',
  deezer: 'Deezer',
  yandex: 'Yandex Music',
  ytmusic: 'YouTube Music',
  apple_music: 'Apple Music',
  soundcloud: 'SoundCloud',
  youtube: 'YouTube',
  tidal: 'Tidal',
  bandcamp: 'Bandcamp',
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  video: <Film className="h-4 w-4" />,
  music: <Music className="h-4 w-4" />,
  other: <Package className="h-4 w-4" />,
}

// main page

export default function StatsMePage() {
  const { t } = useTranslation()
  const [dlStats, setDlStats] = useState<UserStats | null>(null)
  const [dlOverview, setDlOverview] = useState<DlOverview | null>(null)
  const [insightStats, setInsightStats] = useState<InsightStats | null>(null)
  const [musicStats, setMusicStats] = useState<MusicStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      meApi.getStats('/users/me/stats').catch(() => null),
      meApi.getDlOverview(30).catch(() => null),
      meApi.getInsightStats().catch(() => null),
      meApi.getMusicStats().catch(() => null),
    ]).then(([dl, overview, insight, music]) => {
      setDlStats(dl?.data ?? null)
      setDlOverview(overview?.data ?? null)
      setInsightStats(insight?.data ?? null)
      setMusicStats(music?.data ?? null)
    }).catch(() => toast.error(t('common.load_error'))).finally(() => setLoading(false))
  }, [])

  const dlByDay = dlOverview?.downloads_by_day?.slice(-30)?.map(d => ({
    date: formatDayLabel(d.date), count: d.count,
  })) ?? []

  const musicByDay = musicStats?.by_day?.map(d => ({
    date: formatDayLabel(d.date), count: d.count,
  })) ?? []

  const insightByDay = insightStats?.by_day?.map(d => ({
    date: formatDayLabel(d.date), count: d.count,
  })) ?? []

  const colors = chartColors()

  return (
    <div className="space-y-4">
      {/* Downloads */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Download className="h-4 w-4" />
            {t('mystats.downloads', { defaultValue: 'Downloads' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-4">
          {loading ? <SectionSkeleton /> : dlStats ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <StatCard centered label={t('mystats.total', { defaultValue: 'Total' })} value={dlStats.total} />
                <StatCard centered label={t('mystats.this_week', { defaultValue: 'This week' })} value={dlStats.this_week} />
                <StatCard centered label={t('mystats.today', { defaultValue: 'Today' })} value={dlStats.today} />
              </div>

              {dlStats.by_category && Object.keys(dlStats.by_category).length > 0 && (
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(dlStats.by_category).map(([cat, count]) => (
                    <StatCard
                      key={cat}
                      centered
                      icon={CATEGORY_ICONS[cat] ?? <Package className="h-4 w-4" />}
                      label={t(`mystats.cat_${cat}`, { defaultValue: cat })}
                      value={cat === 'music' ? (musicStats?.total ?? count) : count}
                    />
                  ))}
                </div>
              )}

              {dlByDay.length > 1 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2">
                    {t('mystats.last_30d', { defaultValue: 'Last 30 days' })}
                  </p>
                  <MiniBarChart data={dlByDay} color={colors[0]} />
                </div>
              )}

              {dlStats.top_domains.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2">
                    {t('mystats.top_sources', { defaultValue: 'Top sources' })}
                  </p>
                  <HorizontalBars
                    data={dlStats.top_domains.slice(0, 5)}
                    nameKey="domain"
                    valueKey="count"
                    colors={colors}
                  />
                </div>
              )}
            </>
          ) : <EmptyState text={t('mystats.no_data', { defaultValue: 'No data yet' })} />}
        </CardContent>
      </Card>

      {/* Music */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Music className="h-4 w-4" />
            {t('mystats.music', { defaultValue: 'Music' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-4">
          {loading ? <SectionSkeleton /> : musicStats && musicStats.total > 0 ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <StatCard centered icon={<Hash className="h-4 w-4" />} label={t('mystats.total', { defaultValue: 'Total' })} value={musicStats.total} />
                <StatCard centered icon={<CalendarDays className="h-4 w-4" />} label={t('mystats.this_week', { defaultValue: 'This week' })} value={musicStats.this_week} />
                <StatCard centered icon={<Clock className="h-4 w-4" />} label={t('mystats.today', { defaultValue: 'Today' })} value={musicStats.today} />
              </div>

              {musicByDay.length > 1 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2">
                    {t('mystats.last_30d', { defaultValue: 'Last 30 days' })}
                  </p>
                  <MiniBarChart data={musicByDay} color={colors[1]} />
                </div>
              )}

              {musicStats.top_artists && musicStats.top_artists.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <Mic2 className="h-3 w-3" />
                    {t('mystats.top_artists', { defaultValue: 'Top artists' })}
                  </p>
                  <HorizontalBars
                    data={musicStats.top_artists.slice(0, 7)}
                    nameKey="artist"
                    valueKey="count"
                    colors={colors}
                  />
                </div>
              )}

              {musicStats.top_platforms && musicStats.top_platforms.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <BarChart3 className="h-3 w-3" />
                    {t('mystats.platforms', { defaultValue: 'Platforms' })}
                  </p>
                  <HorizontalBars
                    data={musicStats.top_platforms.slice(0, 6).map(p => ({
                      name: PLATFORM_LABELS[p.platform] || p.platform,
                      count: p.count,
                    }))}
                    nameKey="name"
                    valueKey="count"
                    colors={colors}
                  />
                </div>
              )}
            </>
          ) : <EmptyState text={t('mystats.no_music', { defaultValue: 'No music links shared yet' })} />}
        </CardContent>
      </Card>

      {/* AI Summaries */}
      <Card>
        <CardHeader className="px-4 py-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Brain className="h-4 w-4" />
            {t('mystats.ai_summaries', { defaultValue: 'AI Summaries' })}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-4">
          {loading ? <SectionSkeleton /> : insightStats && insightStats.total_summaries > 0 ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <StatCard centered icon={<Hash className="h-4 w-4" />} label={t('mystats.total', { defaultValue: 'Total' })} value={insightStats.total_summaries} />
                <StatCard centered icon={<CalendarDays className="h-4 w-4" />} label={t('mystats.this_week', { defaultValue: 'This week' })} value={insightStats.this_week} />
                <StatCard centered icon={<Clock className="h-4 w-4" />} label={t('mystats.today', { defaultValue: 'Today' })} value={insightStats.today} />
              </div>

              {insightStats.by_command && Object.keys(insightStats.by_command).length > 0 && (
                <div className="space-y-1.5">
                  {Object.entries(insightStats.by_command).map(([cmd, count]) => (
                    <div key={cmd} className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">
                        {cmd === 'summary' ? <FileText className="h-4 w-4" /> : <MessageCircle className="h-4 w-4" />}
                      </span>
                      <span className="text-muted-foreground">/{cmd}</span>
                      <span className="ml-auto tabular-nums font-medium">{count}</span>
                    </div>
                  ))}
                </div>
              )}

              {insightByDay.length > 1 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2">
                    {t('mystats.last_30d', { defaultValue: 'Last 30 days' })}
                  </p>
                  <MiniBarChart data={insightByDay} color={colors[4]} />
                </div>
              )}
            </>
          ) : <EmptyState text={t('mystats.no_ai', { defaultValue: 'No AI summaries yet' })} />}
        </CardContent>
      </Card>
    </div>
  )
}
