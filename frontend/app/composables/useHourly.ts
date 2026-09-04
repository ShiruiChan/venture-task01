import { formatDate, toISO } from './usePeriod'

export interface HourlyPoint {
  ts: number
  at: string
  value: number
}

export interface HourlySeries {
  label: string
  total: number
  points: HourlyPoint[]
}

export interface HourlyResponse {
  date: string
  series: HourlySeries[]
}

export interface HourRow {
  hour: number
  label: string
  current: number | null
  previous: number | null
  delta: number | null
  share: number | null
}

const HOURS = 24

function pad(value: number): string {
  return `${value}`.padStart(2, '0')
}

function hourOf(point: HourlyPoint): number {
  const hour = Number(point.at.slice(11, 13))
  return Number.isFinite(hour) ? hour : -1
}

function byHour(series: HourlySeries | undefined): Array<number | null> {
  const values: Array<number | null> = Array.from({ length: HOURS }, () => null)
  if (!series) return values
  for (const point of series.points ?? []) {
    const hour = hourOf(point)
    if (hour >= 0 && hour < HOURS) values[hour] = point.value
  }
  return values
}

export function hourlyRows(response: HourlyResponse | null | undefined): HourRow[] {
  const current = byHour(response?.series?.[0])
  const previous = byHour(response?.series?.[1])
  const total = current.reduce<number>((sum, value) => sum + (value ?? 0), 0)
  return Array.from({ length: HOURS }, (_, hour) => {
    const now = current[hour] ?? null
    const before = previous[hour] ?? null
    return {
      hour,
      label: `${pad(hour)}:00`,
      current: now,
      previous: before,
      delta: now !== null && before !== null ? now - before : null,
      share: now !== null && total > 0 ? (now / total) * 100 : null,
    }
  })
}

const MONTHS = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

const WEEKDAYS = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']
const WEEKDAYS_SHORT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

export interface DayLabel {
  /** «03.09.2026» */
  date: string
  /** «чт» */
  weekday: string
  /** «3 сентября 2026, четверг» */
  long: string
}

export function dayLabel(day: string | Date): DayLabel {
  const date = typeof day === 'string' ? new Date(`${day}T00:00:00`) : day
  return {
    date: formatDate(date),
    weekday: WEEKDAYS_SHORT[date.getDay()] ?? '',
    long: `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${WEEKDAYS[date.getDay()]}`,
  }
}

/** Подписи колонок: выбранные сутки и та же дата неделей раньше. */
export function hourlyColumns(day: string): { current: DayLabel; previous: DayLabel } {
  const date = new Date(`${day}T00:00:00`)
  const week = new Date(date)
  week.setDate(week.getDate() - 7)
  return { current: dayLabel(date), previous: dayLabel(week) }
}

export function useHourlyApi() {
  const { public: config } = useRuntimeConfig()

  function fetchHourly(day: string | Date) {
    return $fetch<HourlyResponse>(`${config.apiBase}/rarus/hourly`, {
      query: { day: typeof day === 'string' ? day : toISO(day) },
    })
  }

  return { fetchHourly }
}
