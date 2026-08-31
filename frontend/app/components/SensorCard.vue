<script setup lang="ts">
import { formatNumber } from '~/utils/curve'

const props = defineProps<{
  title: string
  hint?: string
  value: number | null
  caption: string
  trend: number | null
  color: string
  series: Array<number | null>
  loading?: boolean
}>()

const trendUp = computed(() => (props.trend ?? 0) >= 0)
const trendText = computed(() => {
  if (props.trend === null || !Number.isFinite(props.trend)) return null
  const abs = Math.abs(props.trend)
  return `${abs.toFixed(abs >= 10 ? 0 : 1).replace('.', ',')}%`
})
</script>

<template>
  <section class="card sensor">
    <header class="sensor__head">
      <span class="sensor__title">{{ title }}</span>
      <span v-if="hint" class="sensor__info" :title="hint" role="img" :aria-label="hint">i</span>
      <span v-if="trendText" class="sensor__trend" :class="trendUp ? 'is-up' : 'is-down'">
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path v-if="trendUp" d="M1.5 9 L5 5.5 L7 7.5 L10.5 3.5" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
          <path v-else d="M1.5 3.5 L5 7 L7 5 L10.5 9" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
          <path v-if="trendUp" d="M7.5 3.5 H10.5 V6.5" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
          <path v-else d="M7.5 9 H10.5 V6" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        {{ trendText }}
      </span>
    </header>

    <p class="sensor__value" :class="{ 'is-loading': loading }">{{ formatNumber(value) }}</p>
    <p class="sensor__caption">{{ caption }}</p>

    <SparkLine class="sensor__spark" :values="series" :color="color" />
  </section>
</template>

<style scoped>
.sensor {
  display: flex;
  flex-direction: column;
  padding: 16px 16px 0;
  overflow: hidden;
  min-height: 132px;
}

.sensor__head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sensor__title {
  font-size: 13px;
  font-weight: 500;
}

.sensor__info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #4aa3f0;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  font-style: italic;
  cursor: help;
  user-select: none;
}

.sensor__trend {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
}

.sensor__trend.is-up { background: #e7f7ef; color: var(--up); }
.sensor__trend.is-down { background: #fdeceb; color: var(--down); }

.sensor__value {
  margin: 6px 0 0;
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  transition: opacity 0.15s ease;
}

.sensor__value.is-loading { opacity: 0.45; }

.sensor__caption {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.sensor__spark {
  margin: 8px -16px 0;
  width: calc(100% + 32px);
}
</style>
