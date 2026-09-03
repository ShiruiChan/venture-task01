<script setup lang="ts">
import { dailyTotals, type ComparisonResponse } from '~/composables/useComparison'
import { customPeriod, formatDate, previousPeriod, resolvePeriod, type Period, type PresetKey } from '~/composables/usePeriod'

const preset = ref<PresetKey>('week')
const offset = ref(0)

// произвольный период: даты для input[type=date], ISO-строки
const customFrom = ref('')
const customTo = ref('')

// пока у custom заполнены не обе даты - остаёмся на прежнем периоде,
// чтобы не уходил запрос с пустыми границами
const period = computed<Period>((prev) => {
  if (preset.value === 'custom') {
    if (!customFrom.value || !customTo.value) return prev ?? resolvePeriod('week')
    // T00:00:00 - чтобы дата разобралась в локальной зоне, а не в UTC
    return customPeriod(new Date(`${customFrom.value}T00:00:00`), new Date(`${customTo.value}T00:00:00`))
  }
  return resolvePeriod(preset.value, offset.value)
})

const { fetchPeriod } = useComparisonApi()

const { data, pending, error, refresh } = await useAsyncData<{
  current: ComparisonResponse
  previous: ComparisonResponse
}>(
  'comparison',
  async () => {
    const [current, previous] = await Promise.all([
      fetchPeriod(period.value),
      fetchPeriod(previousPeriod(period.value)),
    ])
    return { current, previous }
  },
  { watch: [period], server: false },
)

// обновляется и по таймеру, и по кнопке
const updatedAt = ref<Date | null>(null)
watch(data, (value) => {
  if (value) updatedAt.value = new Date()
}, { immediate: true })

const { public: runtime } = useRuntimeConfig()
useAutoRefresh(() => refresh(), Number(runtime.refreshMinutes))

const points = computed(() => (data.value ? dailyTotals(data.value.current.rows, period.value) : []))

const overall = computed(() => data.value?.current.overall ?? null)

function trend(source: 'rarus_total' | 'laser_total' | 'delta'): number | null {
  const now = data.value?.current.overall?.[source]
  const before = data.value?.previous.overall?.[source]
  if (!now || !before) return null
  return ((now - before) / before) * 100
}

const isSingleDay = computed(() => period.value.from.getTime() === period.value.to.getTime())

const caption = computed(() => (isSingleDay.value ? 'человек за день' : `человек за ${points.value.length} дн.`))

const dateLabel = computed(() =>
  isSingleDay.value
    ? formatDate(period.value.to)
    : `${formatDate(period.value.from)} - ${formatDate(period.value.to)}`,
)

function select(key: PresetKey) {
  if (preset.value !== key) offset.value = 0
  preset.value = key
}

function shift(delta: number) {
  offset.value = Math.max(0, offset.value + delta)
}
</script>

<template>
  <div class="page">
    <header class="page__head">
      <h1>Сравнение датчиков подсчета</h1>
    </header>

    <main class="page__body">
      <PeriodBar :preset="preset" :offset="offset" :label="dateLabel" :loading="pending"
                 :updated-at="updatedAt" v-model:custom-from="customFrom" v-model:custom-to="customTo"
                 @select="select" @shift="shift" @refresh="refresh()" />

      <p v-if="error" class="error">
        Не удалось получить данные: {{ error.message }}. Проверьте, что backend запущен на 127.0.0.1:8000.
      </p>

      <div class="cards">
        <SensorCard title="Лазерный датчик" hint="Счётчики «Посещаемость»: проходы из журнала событий"
                    :value="overall?.laser_total ?? null" :caption="caption" :trend="trend('laser_total')"
                    color="var(--laser)" :series="points.map((p) => p.laser)" :loading="pending" />
        <SensorCard title="1С-Рарус" hint="Данные API 1С-Рарус - база для сравнения"
                    :value="overall?.rarus_total ?? null" :caption="caption" :trend="trend('rarus_total')"
                    color="var(--rarus)" :series="points.map((p) => p.rarus)" :loading="pending" />
        <SensorCard title="Разница" hint="Разница между данными Лазерного датчика и 1С-Рарус"
                    :value="overall?.delta ?? null" :caption="caption" :trend="trend('delta')"
                    color="var(--delta)" :series="points.map((p) => p.delta)" :loading="pending" />
      </div>

      <DynamicsChart :points="points" />
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
}

.page__head {
  padding: 16px 32px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}

.page__head h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.page__body {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 26px 32px 40px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

.error {
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #fdeceb;
  color: #93231a;
  font-size: 13px;
}

@media (max-width: 860px) {
  .page__head, .page__body { padding-left: 16px; padding-right: 16px; }
  .cards { grid-template-columns: minmax(0, 1fr); }
}
</style>
