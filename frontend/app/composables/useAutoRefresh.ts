// Автообновление: таймер только на видимой вкладке; при возврате обновляет
// сразу, если интервал уже прошёл. minutes <= 0 отключает.
export function useAutoRefresh(reload: () => unknown | Promise<unknown>, minutes: number) {
  const enabled = minutes > 0
  const intervalMs = Math.max(1, minutes) * 60_000
  // шаг считаем от начала запроса, не от его завершения
  let startedAt = Date.now()
  let timer: ReturnType<typeof setInterval> | null = null
  let running = false

  async function run() {
    // предыдущий запрос ещё в полёте - пропускаем тик
    if (running) return
    running = true
    startedAt = Date.now()
    try {
      await reload()
    } finally {
      running = false
    }
  }

  function start() {
    if (timer || !enabled) return
    timer = setInterval(run, intervalMs)
  }

  function stop() {
    if (!timer) return
    clearInterval(timer)
    timer = null
  }

  function onVisibility() {
    if (document.hidden) {
      stop()
      return
    }
    if (Date.now() - startedAt >= intervalMs) run()
    start()
  }

  onMounted(() => {
    if (!enabled) return
    startedAt = Date.now()
    document.addEventListener('visibilitychange', onVisibility)
    if (!document.hidden) start()
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibility)
    stop()
  })

  return { intervalMs, refreshNow: run }
}
