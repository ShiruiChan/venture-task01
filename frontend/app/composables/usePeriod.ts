export type PresetKey = 'today' | 'yesterday' | 'week' | 'month' | 'year'

export interface Period {
  key: PresetKey
  /** сдвиг окна назад: 1 — предыдущий месяц/год и т.д. */
  offset: number
  from: Date
  to: Date
}

export const PRESET_TITLES: Record<PresetKey, string> = {
  today: 'Сегодня',
  yesterday: 'Вчера',
  week: 'Неделя',
  month: 'Месяц',
  year: 'Год',
}

/** Длина окна в сутках. */
const PRESET_LENGTH: Record<PresetKey, number> = {
  today: 1,
  yesterday: 1,
  week: 7,
  month: 30,
  year: 365,
}

export function startOfDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate())
}

export function addDays(value: Date, days: number): Date {
  const next = new Date(value)
  next.setDate(next.getDate() + days)
  return next
}

export function toISO(value: Date): string {
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${value.getFullYear()}-${month}-${day}`
}

export function formatDate(value: Date): string {
  const day = `${value.getDate()}`.padStart(2, '0')
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  return `${day}.${month}.${value.getFullYear()}`
}

export function periodLength(key: PresetKey): number {
  return PRESET_LENGTH[key]
}

/** Границы окна для пресета с учётом сдвига назад. */
export function resolvePeriod(key: PresetKey, offset = 0): Period {
  const today = startOfDay(new Date())
  const length = PRESET_LENGTH[key]
  if (key === 'week') {
    // календарная неделя целиком: понедельник — воскресенье
    const sinceMonday = (today.getDay() + 6) % 7
    const from = addDays(today, -sinceMonday - offset * 7)
    return { key, offset, from, to: addDays(from, 6) }
  }
  const anchor = key === 'yesterday' ? addDays(today, -1) : today
  const to = addDays(anchor, -offset * length)
  const from = addDays(to, -(length - 1))
  return { key, offset, from, to }
}

/**
 * База для тренда — такое же окно шагом назад. Незакрытый период (текущая
 * неделя, месяц) сравниваем только с тем же числом суток: иначе неполные
 * сутки всегда выглядели бы обвалом.
 */
export function previousPeriod(period: Period): Period {
  const previous = resolvePeriod(period.key, period.offset + 1)
  const today = startOfDay(new Date())
  if (period.to <= today) return previous
  const elapsed = Math.round((today.getTime() - period.from.getTime()) / 86_400_000) + 1
  return { ...previous, to: addDays(previous.from, Math.max(0, elapsed - 1)) }
}
