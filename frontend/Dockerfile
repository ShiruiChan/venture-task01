# Сборка статики.
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
# NUXT_PUBLIC_* вшиваются в статику на этапе сборки - в рантайме их не поменять.
# Внешний API: --build-arg NUXT_PUBLIC_API_BASE=https://api.example.com/api
ARG NUXT_APP_BASE_URL=/
ARG NUXT_PUBLIC_API_BASE=/api
# Минуты; 0 - обновление только кнопкой.
ARG NUXT_PUBLIC_REFRESH_MINUTES=10
ENV NUXT_APP_BASE_URL=$NUXT_APP_BASE_URL NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE \
    NUXT_PUBLIC_REFRESH_MINUTES=$NUXT_PUBLIC_REFRESH_MINUTES
RUN npm run generate

# Раздача.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/.output/public /usr/share/nginx/html
EXPOSE 3000
