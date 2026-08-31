export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      // в проде фронт ходит на тот же origin, что и FastAPI
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
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
    // Совпадает с FRONTEND_MOUNT у FastAPI; для отдельного хостинга — '/'.
    baseURL: process.env.NUXT_APP_BASE_URL || '/app/',
    head: {
      title: 'Сравнение датчиков подсчета',
      htmlAttrs: { lang: 'ru' },
      meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
    },
  },
})
