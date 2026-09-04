<script setup lang="ts">
import { PRESET_TITLES, toISO, type PresetKey } from '~/composables/usePeriod'

const props = defineProps<{
  preset: PresetKey
  offset: number
  label: string
  loading?: boolean
  updatedAt?: Date | null
  customFrom?: string
  customTo?: string
}>()

const emit = defineEmits<{
  (e: 'select', preset: PresetKey): void
  (e: 'shift', delta: number): void
  (e: 'refresh'): void
  (e: 'update:customFrom', value: string): void
  (e: 'update:customTo', value: string): void
}>()

const simple: PresetKey[] = ['today', 'yesterday', 'week']
const steppable: PresetKey[] = ['month', 'year']

const todayISO = toISO(new Date())

const canGoForward = computed(() => props.offset > 0)

const updatedLabel = computed(() => {
  if (!props.updatedAt) return ''
  const hours = `${props.updatedAt.getHours()}`.padStart(2, '0')
  const minutes = `${props.updatedAt.getMinutes()}`.padStart(2, '0')
  return `${hours}:${minutes}`
})
</script>

<template>
  <div class="bar">
    <div class="bar__date">
      <button class="bar__refresh" type="button" :class="{ 'is-busy': loading }"
              title="Обновить данные" aria-label="Обновить данные" @click="emit('refresh')">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9" fill="none" stroke="currentColor"
                stroke-width="1.5" stroke-linecap="round" />
          <path d="M13.6 2.2v2.9h-2.9" fill="none" stroke="currentColor"
                stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <span class="bar__value">{{ label }}</span>
    </div>

    <button v-for="key in simple" :key="key" type="button" class="btn"
            :class="{ 'is-active': preset === key }" @click="emit('select', key)">
      {{ PRESET_TITLES[key] }}
    </button>

    <div v-for="key in steppable" :key="key" class="group">
      <button type="button" class="btn btn--icon" :aria-label="`Предыдущий период: ${PRESET_TITLES[key]}`"
              @click="emit('select', key); emit('shift', 1)">
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M8.5 2.5 L4 7 l4.5 4.5" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <button type="button" class="btn" :class="{ 'is-active': preset === key }" @click="emit('select', key)">
        {{ PRESET_TITLES[key] }}
      </button>
      <button v-if="preset === key && canGoForward" type="button" class="btn btn--icon"
              :aria-label="`Следующий период: ${PRESET_TITLES[key]}`" @click="emit('shift', -1)">
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M5.5 2.5 L10 7 l-4.5 4.5" fill="none" stroke="currentColor"
                stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>

    <button type="button" class="btn" :class="{ 'is-active': preset === 'custom' }"
            @click="emit('select', 'custom')">
      {{ PRESET_TITLES.custom }}
    </button>

    <template v-if="preset === 'custom'">
      <input class="bar__input" type="date" :value="customFrom" :max="todayISO" aria-label="Начало периода"
             @change="emit('update:customFrom', ($event.target as HTMLInputElement).value)">
      <span class="bar__dash" aria-hidden="true">-</span>
      <input class="bar__input" type="date" :value="customTo" :max="todayISO" aria-label="Конец периода"
             @change="emit('update:customTo', ($event.target as HTMLInputElement).value)">
    </template>

    <span v-if="updatedLabel" class="bar__updated">обновлено в {{ updatedLabel }}</span>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.bar__date {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px 0 10px;
  height: 38px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow);
}

.bar__refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}

.bar__refresh:hover { background: #f2f3f5; color: var(--ink); }
.bar__refresh.is-busy svg { animation: spin 0.9s linear infinite; }

@keyframes spin { to { transform: rotate(360deg); } }

.bar__updated {
  margin-left: auto;
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.bar__value {
  font-size: 14px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.btn {
  height: 38px;
  padding: 0 18px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.btn:hover { background: #fafafb; }

.btn.is-active {
  border-color: #d9d5f7;
  background: #f3f1fe;
  color: var(--laser);
}

.btn--icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  width: 34px;
  color: var(--muted);
}

.group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.bar__input {
  height: 38px;
  padding: 0 12px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow);
  font: inherit;
  font-size: 14px;
  color: inherit;
  font-variant-numeric: tabular-nums;
}

.bar__dash {
  color: var(--muted);
}

@media (prefers-reduced-motion: reduce) {
  .bar__refresh.is-busy svg { animation: none; }
}
</style>
