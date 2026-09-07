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

export interface SystemHourData {
  current: number | null
  previous: number | null
  delta: number | null
  share: number | null
}

export interface HourRow {
  hour: number
  label: string
  rarus: SystemHourData
  laser: SystemHourData
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

function createSystemData(current: Array<number | null>, previous: Array<number | null>, hour: number): SystemHourData {
  const now = current[hour] ?? null
  const before = previous[hour] ?? null
  const total = current.reduce<number>((sum, value) => sum + (value ?? 0), 0)
  return {
    current: now,
    previous: before,
    delta: now !== null && before !== null ? now - before : null,
    share: now !== null && total > 0 ? (now / total) * 100 : null,
  }
}

export function hourlyRows(rarusResponse: HourlyResponse | null | undefined, laserResponse: HourlyResponse | null | undefined): HourRow[] {
  const rarusCurrent = byHour(rarusResponse?.series?.[0])
  const rarusPrevious = byHour(rarusResponse?.series?.[1])
  const laserCurrent = byHour(laserResponse?.series?.[0])
  const laserPrevious = byHour(laserResponse?.series?.[1])

  return Array.from({ length: HOURS }, (_, hour) => {
    return {
      hour,
      label: `${pad(hour)}:00`,
      rarus: createSystemData(rarusCurrent, rarusPrevious, hour),
      laser: createSystemData(laserCurrent, laserPrevious, hour),
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

export interface HourlyDataBoth {
  rarus: HourlyResponse
  laser: HourlyResponse
}

export function useHourlyApi() {
  const { public: config } = useRuntimeConfig()

  async function fetchHourlyBoth(day: string | Date): Promise<HourlyDataBoth> {
    const dayStr = typeof day === 'string' ? day : toISO(day)
    const [rarus, laser] = await Promise.all([
      $fetch<HourlyResponse>(`${config.apiBase}/rarus/hourly`, { query: { day: dayStr } }),
      $fetch<HourlyResponse>(`${config.apiBase}/laser/hourly`, { query: { day: dayStr } })
    ])
    return { rarus, laser }
  }

  return { fetchHourlyBoth }
}
