<script setup lang="ts">
import { smoothPath } from '~/utils/curve'

const props = withDefaults(defineProps<{
  values: Array<number | null>
  color?: string
}>(), { color: 'var(--laser)' })

const width = 760
const height = 44

const uid = useId()

const path = computed(() => {
  const points = props.values
    .map((value, index) => ({ value, index }))
    .filter((item): item is { value: number; index: number } => item.value !== null)
  if (points.length === 0) return { line: '', area: '', dot: null }

  const min = Math.min(...points.map((p) => p.value))
  const max = Math.max(...points.map((p) => p.value))
  const span = max - min || 1
  const step = props.values.length > 1 ? width / (props.values.length - 1) : width / 2

  const coords = points.map((p) => ({
    // точка на самом краю обрезалась бы рамкой карточки
    x: Math.min(Math.max(p.index * step, 5), width - 5),
    // сглаженная кривая может выйти за края — оставляем поля сверху и снизу
    y: height - 6 - ((p.value - min) / span) * (height - 14),
  }))

  // единственные сутки в периоде кривой не показать — рисуем точку
  if (coords.length === 1) return { line: '', area: '', dot: coords[0]! }

  const line = smoothPath(coords)
  const area = `${line} L ${coords[coords.length - 1]!.x} ${height} L ${coords[0]!.x} ${height} Z`
  return { line, area, dot: null }
})
</script>

<template>
  <svg class="spark" :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <linearGradient :id="`spark-${uid}`" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.18" />
        <stop offset="100%" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path v-if="path.area" :d="path.area" :fill="`url(#spark-${uid})`" />
    <path v-if="path.line" :d="path.line" fill="none" :stroke="color" stroke-width="2"
          stroke-linecap="round" vector-effect="non-scaling-stroke" />
    <circle v-if="path.dot" :cx="path.dot.x" :cy="path.dot.y" r="3" :fill="color"
            vector-effect="non-scaling-stroke" />
  </svg>
</template>

<style scoped>
.spark {
  display: block;
  width: 100%;
  height: 44px;
}
</style>
