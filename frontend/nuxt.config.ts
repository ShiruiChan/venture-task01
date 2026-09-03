export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      // по умолчанию относительный /api: в dev проксирует nitro, в проде nginx
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      // минуты между обновлениями, вшивается в сборку; 0 отключает
      refreshMinutes: Number(process.env.NUXT_PUBLIC_REFRESH_MINUTES ?? 10),
    },
  },
  nitro: {
    devProxy: {
      '/api': {
        target: process.env.BACKEND_URL || 'http://127.0.0.1:8000/api',
        changeOrigin: true,
      },
    },
  },
  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || '/',
    head: {
      title: 'Сравнение датчиков подсчета',
      htmlAttrs: { lang: 'ru' },
      meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
    },
  },
})
