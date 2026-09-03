import { addDays, toISO, type Period } from './usePeriod'

export interface ComparisonRow {
  division_id: number
  division_name: string
  day: string
  rarus: number | null
  laser: number | null
  delta: number | null
  delta_pct: number | null
  status: string
}

export interface ComparisonOverall {
  rarus_total: number
  laser_total: number
  delta: number
  delta_pct: number
  mean_abs_pct: number
  divisions: number
  critical: number
  warn: number
  missing: number
  idle: number
  ok: number
}

export interface ComparisonResponse {
  date_from: string
  date_to: string
  overall: ComparisonOverall
  divisions: Array<Record<string, unknown>>
  rows: ComparisonRow[]
}

export interface DailyPoint {
  day: string
  rarus: number | null
  laser: number | null
  delta: number | null
}

/** Строки «подразделение × сутки» сворачиваем в дневную динамику. */
export function dailyTotals(rows: ComparisonRow[], period: Period): DailyPoint[] {
  const buckets = new Map<string, { rarus: number | null; laser: number | null }>()
  for (let day = new Date(period.from); day <= period.to; day = addDays(day, 1)) {
    buckets.set(toISO(day), { rarus: null, laser: null })
  }
  for (const row of rows) {
    const bucket = buckets.get(row.day) ?? { rarus: null, laser: null }
    if (row.rarus !== null) bucket.rarus = (bucket.rarus ?? 0) + row.rarus
    if (row.laser !== null) bucket.laser = (bucket.laser ?? 0) + row.laser
    buckets.set(row.day, bucket)
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, values]) => ({
      day,
      rarus: values.rarus,
      laser: values.laser,
      delta: values.rarus !== null && values.laser !== null ? values.laser - values.rarus : null,
    }))
}

export function useComparisonApi() {
  const { public: config } = useRuntimeConfig()

  function fetchPeriod(period: Period) {
    return $fetch<ComparisonResponse>(`${config.apiBase}/comparison`, {
      query: {
        preset: 'custom',
        date_from: toISO(period.from),
        date_to: toISO(period.to),
      },
    })
  }

  return { fetchPeriod }
}
