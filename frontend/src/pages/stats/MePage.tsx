import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Download, Film, Music, Package, Brain,
  Mic2, BarChart3, FileText, MessageCircle,
  CalendarDays, Clock, Hash,
  Link as LinkIcon, Timer, Tv, Globe, Tag,
} from 'lucide-react'
import { meApi, type DlOverview, type InsightStats, type MusicStats, type TldrStats } from '@stats/api/me'
import { Card, CardContent, CardHeader, CardTitle } from '@ui'
import { toast } from '@core/components/ui/toast'
import type { UserStats } from '@core/types/plugin'
import { chartColors, ChartSkeleton, HorizontalBars, MiniBarChart, type MiniBarTooltipProps, SectionSkeleton, StatCard, StatCardSkeleton } from '@core/components/charts'



function EmptyState({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground py-4 text-center">{text}</p>
}

function formatDayLabel(date: string) {
  const d = new Date(date)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatMinutes(mins: number): string {
  if (!mins || mins <= 0) return '0m'
  const total = Math.round(mins)
  if (total < 60) return `${total}m`
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h < 24) return m === 0 ? `${h}h` : `${h}h ${m}m`
  const d = Math.floor(h / 24)
  const rh = h % 24
  return rh === 0 ? `${d}d` : `${d}d ${rh}h`
}

function formatAliasLabel(alias: string): string {
  return alias === '_none' ? '(default)' : alias
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

      {/* TL;DR */}
      <TldrCard
        loading={loading}
        tldr={insightStats?.tldr}
        colors={colors}
      />

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

// ---- TL;DR card ----

function TldrCard({
  loading,
  tldr,
  colors,
}: {
  loading: boolean
  tldr: TldrStats | undefined
  colors: string[]
}) {
  const { t } = useTranslation()

  const byDay = tldr?.by_day?.map(d => ({
    date: formatDayLabel(d.date),
    count: d.count,
    minutes_saved: d.minutes_saved,
    by_alias: d.by_alias,
  })) ?? []

  const aliasTooltip = (props: MiniBarTooltipProps) => {
    if (!props.active || !props.payload || props.payload.length === 0) return null
    const row = props.payload[0].payload as { count: number; minutes_saved: number; by_alias: Record<string, number> }
    const total = row.count
    const entries = Object.entries(row.by_alias ?? {}).sort((a, b) => b[1] - a[1])
    return (
      <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md min-w-[140px]">
        <div className="flex items-baseline justify-between gap-3 mb-1">
          <span className="font-semibold tabular-nums text-foreground">{total}</span>
          <span className="text-muted-foreground">{formatMinutes(row.minutes_saved)} {t('mystats.saved', { defaultValue: 'saved' })}</span>
        </div>
        {entries.length > 0 && (
          <div className="space-y-0.5 pt-1 border-t border-border/60">
            {entries.map(([alias, count]) => {
              const pct = total > 0 ? Math.round((count / total) * 100) : 0
              return (
                <div key={alias} className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-[10px] text-muted-foreground truncate">{formatAliasLabel(alias)}</span>
                  <span className="tabular-nums text-foreground">{count} <span className="text-muted-foreground">({pct}%)</span></span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  const aliasBars = (tldr?.by_alias ?? [])
    .slice(0, 7)
    .map(a => ({ name: formatAliasLabel(a.alias), count: a.count }))

  const kindTotal = tldr ? (tldr.by_kind.youtube + tldr.by_kind.web) : 0
  const ytPct = kindTotal > 0 ? Math.round((tldr!.by_kind.youtube / kindTotal) * 100) : 0
  const webPct = 100 - ytPct

  return (
    <Card>
      <CardHeader className="px-4 py-3">
        <CardTitle className="text-base flex items-center gap-2">
          <LinkIcon className="h-4 w-4" />
          {t('mystats.tldr', { defaultValue: 'TL;DR' })}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-4">
        {loading ? <SectionSkeleton /> : tldr && tldr.total > 0 ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <StatCard centered icon={<Hash className="h-4 w-4" />} label={t('mystats.total', { defaultValue: 'Total' })} value={tldr.total} />
              <StatCard centered icon={<CalendarDays className="h-4 w-4" />} label={t('mystats.this_week', { defaultValue: 'This week' })} value={tldr.this_week} />
              <StatCard centered icon={<Clock className="h-4 w-4" />} label={t('mystats.today', { defaultValue: 'Today' })} value={tldr.today} />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <StatCard
                centered
                variant="success"
                icon={<Timer className="h-4 w-4" />}
                label={t('mystats.time_saved', { defaultValue: 'Time saved' })}
                value={formatMinutes(tldr.minutes_saved)}
              />
              <StatCard
                centered
                icon={<Tv className="h-4 w-4" />}
                label={t('mystats.video_saved', { defaultValue: 'Video' })}
                value={formatMinutes(tldr.video_minutes_saved)}
              />
              <StatCard
                centered
                icon={<Globe className="h-4 w-4" />}
                label={t('mystats.reading_saved', { defaultValue: 'Reading' })}
                value={formatMinutes(tldr.reading_minutes_saved)}
              />
            </div>

            {kindTotal > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><Tv className="h-3 w-3" /> {t('mystats.youtube', { defaultValue: 'YouTube' })} {tldr.by_kind.youtube}</span>
                  <span className="flex items-center gap-1">{tldr.by_kind.web} {t('mystats.web', { defaultValue: 'Web' })} <Globe className="h-3 w-3" /></span>
                </div>
                <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div className="bg-primary" style={{ width: `${ytPct}%` }} />
                  <div className="bg-primary/40" style={{ width: `${webPct}%` }} />
                </div>
              </div>
            )}

            {byDay.length > 1 && (
              <div>
                <p className="text-xs text-muted-foreground mb-2">
                  {t('mystats.last_30d', { defaultValue: 'Last 30 days' })}
                </p>
                <MiniBarChart data={byDay} color={colors[2]} tooltipContent={aliasTooltip} />
              </div>
            )}

            {aliasBars.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                  <Tag className="h-3 w-3" />
                  {t('mystats.tldr_by_alias', { defaultValue: 'By alias' })}
                </p>
                <HorizontalBars
                  data={aliasBars}
                  nameKey="name"
                  valueKey="count"
                  colors={colors}
                />
              </div>
            )}
          </>
        ) : <EmptyState text={t('mystats.no_tldr', { defaultValue: 'No TL;DR usage yet' })} />}
      </CardContent>
    </Card>
  )
}
