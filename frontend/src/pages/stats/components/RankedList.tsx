// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function RankedList<T extends object>({ items, labelKey, valueKey, limit = 10 }: {
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
