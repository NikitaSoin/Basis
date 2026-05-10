# Деплой на сервер

## Требования к серверу
- Ubuntu 22.04+
- Docker + Docker Compose v2 (`docker compose`)
- Git
- Открытый порт 80 (и 443 если нужен HTTPS)

## Первый деплой

### 1. Подключись к серверу и склонируй репозиторий
```bash
ssh user@your-server
git clone git@github.com:your-org/investment-platform.git /opt/invest-platform
cd /opt/invest-platform
```

### 2. Создай .env в корне проекта
```bash
cat > .env << 'END'
POSTGRES_PASSWORD=выбери_надёжный_пароль
END
```

### 3. Создай backend/.env.prod
```bash
cat > backend/.env.prod << 'END'
ANTHROPIC_API_KEY=sk-ant-api03-...твой_ключ...
END
```
> DATABASE_URL прописывается автоматически через docker-compose — не нужно добавлять вручную.

### 4. Запусти контейнеры
```bash
docker compose up --build -d
```

Alembic-миграции применятся автоматически при старте backend-контейнера.

### 5. Проверь что всё работает
```bash
docker compose ps                     # все три контейнера в статусе running
curl http://localhost/api/companies   # должен вернуть JSON
```

Приложение доступно на `http://your-server-ip`.

---

## Автодеплой через GitHub Actions

Каждый push в ветку `main` автоматически деплоится на сервер.

### Добавь секреты в GitHub (Settings → Secrets → Actions):

| Название | Значение |
|---|---|
| `SERVER_HOST` | IP или домен твоего сервера |
| `SERVER_USER` | Пользователь SSH (например `ubuntu`) |
| `SERVER_SSH_KEY` | Содержимое приватного SSH-ключа (весь текст `~/.ssh/id_rsa`) |
| `SERVER_PORT` | Порт SSH (по умолчанию 22, можно не добавлять) |

### Как работает автодеплой:
1. Push в `main` → GitHub Actions запускает воркер
2. Воркер подключается по SSH
3. На сервере: `git pull` + `docker compose up --build -d`
4. Новые образы собираются, контейнеры перезапускаются с нулевым downtime БД

---

## Полезные команды

```bash
# Логи backend
docker compose logs -f backend

# Перезапустить только backend
docker compose restart backend

# Зайти в контейнер backend
docker compose exec backend bash

# Запустить генерацию AI-анализа
docker compose exec backend python -m scripts.generate_analysis

# Бэкап БД
docker compose exec db pg_dump -U postgres invest_db > backup_$(date +%Y%m%d).sql
```

---

## HTTPS (опционально)

Для HTTPS используй [nginx-proxy + Let's Encrypt](https://github.com/nginx-proxy/acme-companion):

```bash
docker network create nginx-proxy
```

Добавь в frontend-сервис в docker-compose.yml:
```yaml
environment:
  VIRTUAL_HOST: your-domain.com
  LETSENCRYPT_HOST: your-domain.com
  LETSENCRYPT_EMAIL: your@email.com
networks:
  - nginx-proxy
  - default
```
