<script setup lang="ts">
import { hourlyColumns, type HourRow } from '~/composables/useHourly'
import { formatNumber } from '~/utils/curve'

const props = defineProps<{
  rows: HourRow[]
  day: string
  loading?: boolean
  error?: string | null
  note?: string | null
}>()

const showAll = ref(false)

function isEmpty(row: HourRow): boolean {
  return !(row.current ?? 0) && !(row.previous ?? 0)
}

const visibleRows = computed(() => (showAll.value ? props.rows : props.rows.filter((row) => !isEmpty(row))))

const hiddenCount = computed(() => props.rows.length - props.rows.filter((row) => !isEmpty(row)).length)

const columns = computed(() => hourlyColumns(props.day))

const peak = computed(() => Math.max(0, ...props.rows.map((row) => row.current ?? 0)))

const totals = computed(() => {
  const current = props.rows.reduce<number>((sum, row) => sum + (row.current ?? 0), 0)
  const previous = props.rows.reduce<number>((sum, row) => sum + (row.previous ?? 0), 0)
  return { current, previous, delta: current - previous }
})

function barWidth(row: HourRow): string {
  if (!peak.value || row.current === null) return '0%'
  return `${(row.current / peak.value) * 100}%`
}

function signed(value: number | null): string {
  if (value === null) return '-'
  return `${value > 0 ? '+' : ''}${formatNumber(value)}`
}

function share(value: number | null): string {
  if (value === null) return '-'
  return `${value.toFixed(1).replace('.', ',')}%`
}
</script>

<template>
  <section class="card hours">
    <header class="hours_head">
      <div class="hours_heading">
        <h2 class="hours_title">
          Посещаемость по часам за {{ columns.current.long }}
          <span class="hours_hint" title="Виджет 1С-Рарус «Посещаемость по часам»; данные только по одним суткам"
                role="img" aria-label="Виджет 1С-Рарус «Посещаемость по часам»; данные только по одним суткам">i</span>
        </h2>
        <p class="hours_sub">
          Источник - 1С-Рарус<template v-if="note">, {{ note }}</template>.
          Для сравнения рядом тот же день недели неделей раньше, {{ columns.previous.long }}.
        </p>
      </div>
      <button v-if="hiddenCount" type="button" class="hours_toggle" @click="showAll = !showAll">
        {{ showAll ? 'Только рабочие часы' : `Все часы (+${hiddenCount})` }}
      </button>
    </header>

    <p v-if="error" class="hours_note hours_note--error">Часовая детализация недоступна: {{ error }}</p>
    <p v-else-if="loading && !rows.length" class="hours_note">Загружаем часовую детализацию...</p>
    <p v-else-if="!visibleRows.length" class="hours_note">За эти сутки проходов нет.</p>

    <div v-else class="hours_scroll" :class="{ 'is-loading': loading }">
      <table class="hours_table">
        <thead>
          <tr>
            <th scope="col" class="col-hour">Час</th>
            <th scope="col">
              <span class="col_name">Этот день</span>
              <span class="col_note">{{ columns.current.date }}, {{ columns.current.weekday }}</span>
            </th>
            <th scope="col">
              <span class="col_name">Неделей раньше</span>
              <span class="col_note">{{ columns.previous.date }}, {{ columns.previous.weekday }}</span>
            </th>
            <th scope="col">
              <span class="col_name">Дельта к неделе</span>
              <span class="col_note">человек</span>
            </th>
            <th scope="col">
              <span class="col_name">Доля</span>
              <span class="col_note">от суток</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in visibleRows" :key="row.hour">
            <th scope="row" class="col-hour">{{ row.label }}</th>
            <td class="num num--bar">
              <span class="bar" :style="{ width: barWidth(row) }" aria-hidden="true" />
              <span class="num_value">{{ formatNumber(row.current) }}</span>
            </td>
            <td class="num is-muted">{{ formatNumber(row.previous) }}</td>
            <td class="num" :class="row.delta === null || row.delta === 0 ? 'is-muted'
                                    : row.delta > 0 ? 'is-up' : 'is-down'">
              {{ signed(row.delta) }}
            </td>
            <td class="num is-muted">{{ share(row.share) }}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" class="col-hour">Итого</th>
            <td class="num">{{ formatNumber(totals.current) }}</td>
            <td class="num is-muted">{{ formatNumber(totals.previous) }}</td>
            <td class="num" :class="totals.delta === 0 ? 'is-muted' : totals.delta > 0 ? 'is-up' : 'is-down'">
              {{ signed(totals.delta) }}
            </td>
            <td class="num is-muted">100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  </section>
</template>

<style scoped>
.hours {
  padding: 16px 18px 14px;
}

.hours_head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.hours_heading {
  min-width: 0;
}

.hours_title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.hours_hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: 1px;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #ececf1;
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  cursor: help;
}

.hours_sub {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.hours_toggle {
  margin-left: auto;
  flex: none;
  padding-top: 2px;
  border: 0;
  background: none;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.hours_toggle:hover {
  color: var(--ink);
}

.hours_note {
  margin: 14px 0 4px;
  color: var(--muted);
  font-size: 13px;
}

.hours_note--error {
  color: var(--down);
}

.hours_scroll {
  margin-top: 12px;
  overflow-x: auto;
  transition: opacity 0.15s ease;
}

.hours_scroll.is-loading {
  opacity: 0.55;
}

.hours_table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.hours_table th,
.hours_table td {
  padding: 7px 10px;
  text-align: right;
  white-space: nowrap;
}

.hours_table thead th {
  padding-bottom: 9px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-weight: 600;
  vertical-align: bottom;
}

/* заголовок колонки в две строки: что за столбец и за какую дату */
.col_name {
  display: block;
  color: var(--ink);
  font-size: 12px;
  font-weight: 600;
}

.col_note {
  display: block;
  margin-top: 1px;
  font-size: 11px;
  font-weight: 500;
}

.hours_table tbody tr + tr th,
.hours_table tbody tr + tr td {
  border-top: 1px solid #f3f3f6;
}

.hours_table tbody tr:hover th,
.hours_table tbody tr:hover td {
  background: #fafafc;
}

.col-hour {
  width: 1%;
  text-align: left !important;
  font-weight: 600;
}

.num {
  font-weight: 600;
}

/* столбик заливки прячем за числом - масштаб часа виден без графика */
.num--bar {
  position: relative;
}

.bar {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  height: 18px;
  border-radius: 4px;
  background: rgba(245, 166, 35, 0.18);
}

.num_value {
  position: relative;
}

.is-muted {
  color: var(--muted);
  font-weight: 500;
}

.is-up {
  color: var(--up);
}

.is-down {
  color: var(--down);
}

.hours_table tfoot th,
.hours_table tfoot td {
  border-top: 1px solid var(--line);
  font-weight: 700;
}

@media (max-width: 720px) {
  .hours_head {
    flex-direction: column;
    gap: 6px;
  }

  .hours_toggle {
    margin-left: 0;
  }

  .hours_table th,
  .hours_table td {
    padding: 6px 8px;
  }
}
</style>
