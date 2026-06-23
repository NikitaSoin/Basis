# Фронт НЕ собирается на сервере (это роняло сборку Timeweb по памяти, OOM, когда бандл
# вырос — и фронт-приложение залипало на последней удачной сборке). Вместо этого отдаём
# уже собранный build/ — его собираю локально (npm run build) и коммичу в репозиторий.
# ВАЖНО: перед коммитом фронт-изменений всегда пересобирать build/ (см. docs/work-journal).
FROM nginx:alpine
COPY build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
