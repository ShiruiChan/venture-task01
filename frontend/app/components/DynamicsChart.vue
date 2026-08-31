<script setup lang="ts">
import type { DailyPoint } from '~/composables/useComparison'
import { niceTicks, smoothPath, formatNumber, type Pt } from '~/utils/curve'

const props = defineProps<{
  points: DailyPoint[]
  compact?: boolean
}>()

const SERIES = [
  { key: 'rarus', title: '1С-Рарус', color: 'var(--rarus)' },
  { key: 'laser', title: 'Лазер', color: 'var(--laser)' },
] as const

type SeriesKey = (typeof SERIES)[number]['key']

const visible = ref<Record<SeriesKey, boolean>>({ rarus: true, laser: true })

const box = ref<HTMLElement | null>(null)
const width = ref(960)
const height = 232
const pad = { top: 14, right: 18, bottom: 30, left: 58 }

let observer: ResizeObserver | null = null
onMounted(() => {
  if (!box.value) return
  observer = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.max(320, entry.contentRect.width)
  })
  observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const plotWidth = computed(() => width.value - pad.left - pad.right)
const plotHeight = height - pad.top - pad.bottom

const maxValue = computed(() => {
  const values = props.points.flatMap((p) => [
    visible.value.rarus ? p.rarus : null,
    visible.value.laser ? p.laser : null,
  ])
  const filtered = values.filter((v): v is number => v !== null)
  return filtered.length ? Math.max(...filtered) : 0
})

const ticks = computed(() => niceTicks(maxValue.value || 10, 5))
const scaleMax = computed(() => ticks.value[ticks.value.length - 1] || 1)

const step = computed(() => (props.points.length > 1 ? plotWidth.value / (props.points.length - 1) : 0))

function xAt(index: number): number {
  return pad.left + index * step.value
}

function yAt(value: number): number {
  return pad.top + plotHeight - (value / scaleMax.value) * plotHeight
}

/** Разрывы в данных не соединяем: каждый непрерывный участок — отдельная кривая. */
function segments(key: SeriesKey): string[] {
  const paths: string[] = []
  let current: Pt[] = []
  props.points.forEach((point, index) => {
    const value = point[key]
    if (value === null) {
      if (current.length) paths.push(smoothPath(current))
      current = []
      return
    }
    current.push({ x: xAt(index), y: yAt(value) })
  })
  if (current.length) paths.push(smoothPath(current))
  return paths.filter(Boolean)
}

/** Сутки без соседей (начало периода, дыры в данных) — кривой их не показать, ставим точку. */
function orphans(key: SeriesKey): Pt[] {
  return props.points
    .map((point, index) => ({ point, index }))
    .filter(({ point, index }) => {
      if (point[key] === null) return false
      const before = props.points[index - 1]?.[key] ?? null
      const after = props.points[index + 1]?.[key] ?? null
      return before === null && after === null
    })
    .map(({ point, index }) => ({ x: xAt(index), y: yAt(point[key] as number) }))
}

const WEEKDAYS = ['ВС', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']

const isWeek = computed(() => props.points.length <= 8)

function labelFor(day: string): string {
  const date = new Date(`${day}T00:00:00`)
  if (isWeek.value) return WEEKDAYS[date.getDay()] ?? ''
  return `${`${date.getDate()}`.padStart(2, '0')}.${`${date.getMonth() + 1}`.padStart(2, '0')}`
}

/** На длинных периодах подписей на оси должно остаться не больше восьми. */
const labelStride = computed(() => Math.max(1, Math.ceil(props.points.length / 8)))

const hover = ref<number | null>(null)

const hoverPoint = computed(() => (hover.value === null ? null : props.points[hover.value] ?? null))

function onMove(event: MouseEvent) {
  if (!props.points.length || !box.value) return
  const rect = box.value.getBoundingClientRect()
  const x = event.clientX - rect.left - pad.left
  const index = step.value > 0 ? Math.round(x / step.value) : 0
  hover.value = Math.min(props.points.length - 1, Math.max(0, index))
}

const tooltip = computed(() => {
  if (hover.value === null || !hoverPoint.value) return null
  const point = hoverPoint.value
  const values = [point.rarus, point.laser].filter((v): v is number => v !== null)
  const anchorY = values.length ? yAt(Math.max(...values)) : pad.top + plotHeight / 2
  const x = xAt(hover.value)
  const flip = x + 190 > width.value
  return {
    x: flip ? x - 14 : x + 14,
    y: Math.max(pad.top, anchorY - 20),
    flip,
    point,
  }
})

function toggle(key: SeriesKey) {
  const other = key === 'rarus' ? 'laser' : 'rarus'
  // последнюю включённую серию не гасим — иначе график остаётся пустым
  if (visible.value[key] && !visible.value[other]) return
  visible.value = { ...visible.value, [key]: !visible.value[key] }
}
</script>

<template>
  <section class="card chart">
    <header class="chart__head">
      <h2 class="chart__title">Динамика подсчета посетителей</h2>
      <div class="chart__legend">
        <button v-for="series in SERIES" :key="series.key" type="button" class="legend"
                :class="{ 'is-off': !visible[series.key] }" :style="{ color: series.color }"
                @click="toggle(series.key)">
          {{ series.title }}
        </button>
      </div>
    </header>

    <div ref="box" class="chart__plot" @mousemove="onMove" @mouseleave="hover = null">
      <svg :width="width" :height="height" role="img" aria-label="Динамика подсчета посетителей">
        <g class="grid">
          <template v-for="tick in ticks" :key="tick">
            <line :x1="pad.left" :x2="width - pad.right" :y1="yAt(tick)" :y2="yAt(tick)" />
            <text :x="pad.left - 12" :y="yAt(tick) + 4" text-anchor="end">{{ formatNumber(tick) }}</text>
          </template>
        </g>

        <g class="axis">
          <template v-for="(point, index) in points" :key="point.day">
            <text v-if="index % labelStride === 0" :x="xAt(index)" :y="height - 8" text-anchor="middle">
              {{ labelFor(point.day) }}
            </text>
          </template>
        </g>

        <line v-if="hover !== null" class="cursor" :x1="xAt(hover)" :x2="xAt(hover)"
              :y1="pad.top" :y2="pad.top + plotHeight" />

        <template v-for="series in SERIES" :key="series.key">
          <template v-if="visible[series.key]">
            <path v-for="(d, i) in segments(series.key)" :key="i" :d="d" fill="none"
                  :stroke="series.color" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <circle v-for="(dot, i) in orphans(series.key)" :key="`dot-${i}`" :cx="dot.x" :cy="dot.y"
                    r="3" :fill="series.color" />
            <circle v-if="hover !== null && hoverPoint?.[series.key] !== null && hoverPoint"
                    :cx="xAt(hover)" :cy="yAt(hoverPoint[series.key] as number)" r="4"
                    :fill="series.color" stroke="#fff" stroke-width="2" />
          </template>
        </template>
      </svg>

      <div v-if="tooltip" class="tip" :class="{ 'tip--flip': tooltip.flip }"
           :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }">
        <p class="tip__day">{{ labelFor(tooltip.point.day) }} · {{ tooltip.point.day.split('-').reverse().join('.') }}</p>
        <p v-if="visible.rarus">1С-Рарус <b>{{ formatNumber(tooltip.point.rarus) }}</b></p>
        <p v-if="visible.laser">Лазер <b>{{ formatNumber(tooltip.point.laser) }}</b></p>
        <p v-if="visible.rarus && visible.laser && tooltip.point.delta !== null">
          Расхождение <b>{{ tooltip.point.delta > 0 ? '+' : '' }}{{ formatNumber(tooltip.point.delta) }}</b>
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chart {
  padding: 16px 18px 8px;
}

.chart__head {
  display: flex;
  align-items: center;
  gap: 16px;
}

.chart__title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.chart__legend {
  margin-left: auto;
  display: flex;
  gap: 12px;
}

.legend {
  border: 0;
  background: none;
  padding: 0;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.legend.is-off {
  color: var(--muted) !important;
  text-decoration: none;
}

.chart__plot {
  position: relative;
  margin-top: 8px;
}

svg { display: block; }

.grid line {
  stroke: #e9e9ee;
  stroke-dasharray: 2 4;
}

.grid text,
.axis text {
  fill: var(--muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.axis text { font-size: 10px; letter-spacing: 0.02em; }

.cursor {
  stroke: #d7d7de;
  stroke-width: 1;
}

.tip {
  position: absolute;
  transform: translateY(-50%);
  min-width: 140px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #2b2b31;
  color: #fff;
  font-size: 12px;
  line-height: 1.55;
  pointer-events: none;
  box-shadow: 0 6px 20px rgba(20, 20, 30, 0.22);
}

.tip--flip { transform: translate(-100%, -50%); }

.tip p { margin: 0; }
.tip b { font-weight: 700; }

.tip__day {
  margin-bottom: 2px !important;
  color: #a8a8b3;
  font-size: 11px;
}

.tip::after {
  content: '';
  position: absolute;
  top: 50%;
  margin-top: -5px;
  border: 5px solid transparent;
}

.tip:not(.tip--flip)::after {
  left: -10px;
  border-right-color: #2b2b31;
}

.tip--flip::after {
  right: -10px;
  border-left-color: #2b2b31;
}
</style>
