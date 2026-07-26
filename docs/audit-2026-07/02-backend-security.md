# Аудит бэкенда Basis — архитектура + безопасность

Дата: 2026-07-26. Область: `backend/`. Один проход, код не редактировался.
Живой прод проверялся только безопасными GET (`/api/debug/env`, `/api/debug/ping`).

---

## ТОП-10 по приоритету

### CRITICAL

**C1. Весь роутер `/api/debug/*` открыт наружу без авторизации (30+ эндпоинтов)**
- Файл: `app/api/debug.py` (весь файл) + `app/main.py:951` (`include_router(debug_router)` — без `dependencies=`); сам `APIRouter()` в `debug.py:11` тоже без зависимостей.
- Что не так: ни один debug-эндпоинт не требует токена. Роутер содержит три класса опасных операций (см. полную классификацию в разделе ниже):
  - **УНИЧТОЖЕНИЕ ДАННЫХ** (аноним может стереть прод-данные): `POST /debug/purge-future-macro`, `/debug/purge-implausible-macro-news`, `/debug/reset-report-watch`, `/debug/purge-girbo-backlog`, `/debug/purge-news-junk-reports?dry_run=false`, `/debug/purge-shallow-geo-digest`, `/debug/trigger-lenta-cleanup?keep_days=0` (обнулит всю Ленту новостей), `/debug/fix-cmasf-source-typo` (UPDATE).
  - **ТРАТА ДЕНЕГ/лимитов** (аноним жжёт LLM-бюджет и MOEX rate-limit): `POST /debug/trigger-macro-sync` (десяток LLM-вызовов), `/debug/trigger-news`, `/debug/trigger-report-watch`, `/debug/trigger-geo-digest`, `/debug/trigger-macro-analytics`, `/debug/trigger-macro-interpretation`, `/debug/trigger-news-strikes`, `/debug/trigger-calendar`, `/debug/trigger-instrument-history`, `/debug/trigger-index-backfill` и др.
  - **РАСКРЫТИЕ ВНУТРЕННОСТЕЙ**: `/debug/env`, `/debug/connectivity`, `/debug/tinkoff`, `/debug/jobs-health`, `/debug/selftest`, `/debug/chronicle-stats`.
- Чем грозит: полное разрушение витринных данных без аутентификации; неограниченный расход платного LLM-бюджета; отказ в обслуживании; разведка инфраструктуры.
- Что сделать: повесить на роутер общую зависимость-гейт (`dependencies=[Depends(require_debug_token)]`, сверять заголовок с `DEBUG_TOKEN` из env), либо включать роутер только при `ENABLE_DEBUG=1`. Разовые seed/purge — вынести из HTTP в management-скрипты (`scripts/`), не в постоянные роуты.
- Трудоёмкость: **S** (одна зависимость на роутер) — М, если выносить seed/purge в скрипты.

**C2. `JWT_SECRET_KEY` c хардкод-дефолтом; в `.env`/деплой-конфиге не задан**
- Файл: `app/auth.py:11` — `SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "changeme-use-env-in-production")`.
- Что не так: переменной нет в `backend/.env`, нет в `start.sh`/`Dockerfile`/`Procfile`. Если она не проставлена в панели Timeweb, токены подписываются ПУБЛИЧНО ИЗВЕСТНЫМ ключом. `/debug/env` её не показывает, поэтому с бою подтвердить нельзя — **требует проверки владельцем**.
- Чем грозит: при дефолтном ключе любой может подделать JWT `{"sub":"<id>"}` и стать любым пользователем → читать/удалять чужие портфели, историю ассистента, отчёты Обозревателя. Полный обход всей аутентификации.
- Что сделать: сгенерировать длинный случайный `JWT_SECRET_KEY`, положить в env Timeweb; убрать «рабочий» дефолт — падать при отсутствии в проде (`RuntimeError`, а не тихий фолбэк).
- Трудоёмкость: **S**.

**C3. `GET /api/debug/env` раскрывает инфраструктуру (подтверждено вживую)**
- Файл: `app/api/debug.py:145-173`. Живой ответ прод (2026-07-26):
  - хост/порт/имя/юзер БД: `postgresql://***:***@faf269010a9d75c19b7d059b.twc1.net:5432/default_db` (пароль замаскирован — ОК, остальное нет);
  - длины всех секретов (TINKOFF 88, ANTHROPIC 108, DEEPSEEK 35, FRED 32) — помогает атакующему;
  - URL CF-Worker-релеев: `minfin-proxy`/`webfetch-proxy`/`fred-proxy.nikitasoin.workers.dev` — их теперь можно долбить/абузить напрямую.
- Чем грозит: цель для атаки на managed-PG (хост известен), абуз незащищённых прокси-воркеров, разведка.
- Что сделать: закрывается вместе с C1 (гейт роутера). Дополнительно — не отдавать хост БД и длины ключей даже под токеном.
- Трудоёмкость: **S**.

### HIGH

**H1. SSRF: сервер ходит по хосту/URL из параметра запроса, без авторизации**
- Файлы: `app/api/debug.py` — `/debug/trace?host=`, `/debug/sni?host=`, `/debug/mtu?host=` (сырой TCP/TLS к произвольному хосту); `app/api/agents.py:119` `/agents/analyze-document` (`fetch_document(url)` по любому URL, `get_current_user_optional` — аноним разрешён); `/agents/web-search`, `/agents/telegram/{channel}`.
- Что не так: атакующий заставляет сервер устанавливать соединения к произвольным адресам (внутренняя сеть, metadata-эндпоинты облака, порт-скан изнутри периметра) + тратит LLM на `analyze-document`.
- Чем грозит: SSRF-разведка внутренней сети, эксфильтрация через сервер, расход бюджета.
- Что сделать: авторизовать эти роуты; для `analyze-document` — allowlist схем/хостов (только http/https, запрет private/link-local диапазонов и `*.internal`/metadata IP).
- Трудоёмкость: **M**.

**H2. Публичные LLM-эндпоинты «жгут деньги» без авторизации**
- Файлы: `app/api/agents.py` — `POST /agents/review/{ticker}/{tab}`, `POST /agents/review-bond/{secid}`, `POST /agents/analyze-document`. Только `run-macro-addendum` ограничен пилот-тикерами; ревизии работают по ЛЮБОЙ компании/облигации, а `force=true` обходит 12-часовой кэш.
- Чем грозит: аноним в цикле с `force=true` по 262 тикерам × вкладки неограниченно расходует LLM-бюджет.
- Что сделать: `Depends(get_current_user)` + троттлинг per-user; для демо оставить только кэш-чтение анонимам, запуск (`force`) — под токеном.
- Трудоёмкость: **S-M**.

**H3. `GET /api/debug/echo?kb=5000` + отсутствие любого rate-limiting = DoS-усилитель**
- Файл: `app/api/debug.py:458-466` — `os.urandom(kb*1024)` до 5 МБ несжимаемых байт на запрос, аноним. Rate-limiting на платформе нет нигде (кроме кулдауна email-кодов).
- Чем грозит: дешёвая амплификация трафика/памяти; brute-force `/auth/login` (см. M3).
- Что сделать: убрать/закрыть `echo` (уходит с C1); добавить общий лимитер (slowapi) на аноним-роуты и на `/auth/*`.
- Трудоёмкость: **M** (лимитер) / S (echo).

### MEDIUM

**M1. `GET /api/users/{user_id}` и `POST /api/users` — полностью публичны**
- Файл: `app/api/users.py:17-22` (GET без auth, отдаёт email по порядковому id → перечисление адресов) и `:10-14` (POST создаёт аккаунт в обход email-подтверждения из `/auth/register`).
- Чем грозит: сбор базы email пользователей по инкременту id; создание аккаунтов мимо верификации.
- Что сделать: закрыть `GET /users/{id}` под auth (или отдавать только себя); удалить/закрыть публичный `POST /users` — регистрация только через `/auth/register`.
- Трудоёмкость: **S**.

**M2. CORS: доверенный credentialed-origin — любой `*.twc1.net`**
- Файл: `app/main.py:938` — `allow_origin_regex=r"https://([a-z0-9-]+\.)*(inbasis\.ru|twc1\.net)"` при `allow_credentials=True`.
- Что не так: `twc1.net` — общий домен хостинга Timeweb; ЛЮБОЙ чужой тенант на поддомене `*.twc1.net` становится доверенным origin с кредами. (Токен сейчас в заголовке `Authorization`, не в cookie, что снижает остроту, но регэксп всё равно слишком широк.)
- Что сделать: сузить до реальных доменов фронта/бэка (`inbasis.ru`, `www.inbasis.ru` и конкретный поддомен API), без общего `twc1.net`.
- Трудоёмкость: **S**.

**M3. Нет троттлинга на `/auth/login` и `/auth/register`**
- Файл: `app/api/auth.py:48` — `login` без ограничения попыток (bcrypt защищает хеш, но не от онлайн-перебора/забивания). Кулдаун есть только у email-кодов.
- Чем грозит: перебор паролей, спам регистраций.
- Что сделать: лимитер per-IP/email на `/auth/*`.
- Трудоёмкость: **S-M**.

### LOW

**L1. Path-traversal-непоследовательность в `business-model`**
- Файл: `app/api/companies.py:306-308` — `COMPANIES_DIR / ticker.upper() / "business_model.md"` БЕЗ `_safe(ticker)`, тогда как все соседние file-роуты (`financials`, `governance`, `market`, `macro`, `geo`, `institutions`) через `_safe()`. FastAPI не матчит `/` в path-параметре, поэтому эксплуатация ограничена одним уровнем `..` и файлом строго с именем `business_model.md` — практический риск низкий, но это брешь в defense-in-depth и рассинхрон с конвенцией.
- Что сделать: обернуть в `_safe(ticker)`, как соседей.
- Трудоёмкость: **S**.

---

## Детали по разделам

### 1. Debug-эндпоинты: полная классификация (все без auth)

**Мутируют данные (POST):** `purge-future-macro`, `purge-implausible-macro-news`, `reset-report-watch`, `purge-girbo-backlog`, `purge-news-junk-reports`, `purge-shallow-geo-digest`, `fix-cmasf-source-typo`, `trigger-lenta-cleanup`, `seed-fixed-capital-investment-q1-2026`, `seed-weekly-inflation-jul20-2026`, `trigger-company-rss?force_reset=true`, `reset`-ветки в trigger-*.

**Тратят деньги/лимиты (LLM или тяжёлый MOEX/GIRBO):** `trigger-macro-sync`, `trigger-macro-interpretation`, `trigger-macro-analytics`, `trigger-news`, `trigger-report-watch`, `trigger-geo-digest`, `trigger-geo-digest-backfill-strikes`, `trigger-news-strikes`, `trigger-company-rss`, `trigger-smartlab-detect`, `trigger-calendar`, `trigger-instrument-history`, `trigger-index-backfill`, `trigger-refresh-funds`, `trigger-risk-free-rate`. (`trigger-macro-verification`, `trigger-geo-frontline-sync` — по докстрингам без LLM, дёшевы, но всё равно аноним-триггеры.)

**Раскрывают внутренности (GET):** `env` (подтверждено), `connectivity` (топология сети + статус пула БД + доступность БД), `tinkoff` (дамп инструментов + длина токена), `trace`/`sni`/`mtu` (SSRF-примитив, см. H1), `echo` (DoS, см. H3), `selftest`, `jobs-health`, `ping`, `report-watch-trace`/`report-watch-diag` (INN-маппинг, внешние данные), `chronicle-stats`/`chronicle-preview`.

Итог: `debug.py` — 1382 строки, 2-й по размеру файл в `app/`; фактически это набор одноразовых админ-скриптов, оформленных как постоянные HTTP-роуты. Помимо гейта авторизации, seed/purge стоит вынести в `scripts/` как management-команды.

### 2. Секреты в репозитории
- `backend/.env` **не отслеживается git** (в `.gitignore`), реальные секреты в историю НЕ утекали. `git log -p` по `*.env*` за всю историю показывает только плейсхолдеры (`your_anthropic_api_key_here`, `postgresql://postgres@localhost`).
- Захардкоженных ключей/паролей в коде (`app/`, `scripts/`, `config/`) не найдено — везде `os.environ`. Единственное исключение по смыслу — дефолт `JWT_SECRET_KEY` (C2), это не утечка, а слабый фолбэк.
- `frontend/Basis/.env.production` содержит только публичный `REACT_APP_API_URL` — не секрет.

### 3. Аутентификация и IDOR
- Портфели (`portfolios.py`), сохранённые фильтры (`screener.py`), диалоги ассистента (`assistant.py`), отчёты Обозревателя (`observer.py`) — **везде корректная проверка `user_id`/`403`**, IDOR не найден. `get_portfolio_by_id` + сверка `portfolio.user_id == current_user.id` во всех роутах портфеля.
- Дыры аутентификации — вне портфельного контура: весь `debug` (C1), `users/{id}`+`POST users` (M1), agents-LLM (H1/H2). `market/maps/*` и `market/macro` используют `get_current_user_optional` (аноним разрешён) — это витрина, чтения без приватных данных, приемлемо.

### 4. SQL-инъекции
- Пользовательские значения ВЕЗДЕ через bind-параметры (`:x`) — проверено в `email_codes.py`, `companies.py`, `agent_tools.py`, `chronicle`-запросах.
- f-string в SQL встречается в 3 местах и во всех безопасен: `asset_data.py:142,152` и `instrument_history.py:77` подставляют имена таблиц из внутренних констант (`_META_TABLE[asset_class]`, где `asset_class` валидируется по `SOURCES`); `agent_tools.py:176` подставляет `days` — целое, зажатое `max(7, min(int(days), 1825))`. Пользовательские строки в SQL-текст не попадают. **Инъекция не эксплуатируется.**

### 5. CORS / rate limiting
- CORS — см. M2 (слишком широкий регэксп `twc1.net`).
- Rate limiting **отсутствует** как класс (нет slowapi/limiter). Единственное ограничение — кулдаун/лимит email-кодов в `email_codes.py`. См. H3/M3.

### 6. Размеры, связность, кроны
- Топ-10 по размеру (`app/`): `services/portfolio.py` 1443 · `api/debug.py` 1382 · `services/report_watch.py` 1232 · `services/calendar_events.py` 1154 · `api/market.py` 1118 · `main.py` 967 · `api/companies.py` 775 · `services/geo_digest.py` 663 · `services/macro_cb_sync.py` 663 · `services/portfolio_quality_v2.py` 643.
- **main.py (967 строк):** ~17 cron-джобов + ~10 startup-задач инлайн в `lifespan`. Кроны идут через `run_in_executor`, КАЖДЫЙ держит свою `SessionLocal` на всё время. Пул БД мал: `pool_size=5, max_overflow=10` (макс 15). Наложения:
  - **Утренний кластер 06:00–06:45:** `asset_data_refresh` (06:00, облигации ~15–20 мин) ⟂ `macro_ingest` (06:30, тяжёлый: ЦБ+FRED+Росстат+Минфин+hh+Urals+WB+Yahoo+LLM-аналитика) ⟂ `calendar_refresh` (06:45, per-ticker MOEX, минуты). Плюс в это же окно ежечасные `news_feed` (:05), `geo_digest` (:10), `macro_rate_watch` (:20).
  - **Вечерний кластер 20:30–21:00:** `earnings_digest` (20:30) ⟂ `report_watch` (20:45, LLM+GIRBO) ⟂ `geopolitics` (21:00, DeepSeek Pro).
  - Джобы добавляются БЕЗ `max_instances=1`/`coalesce`/`misfire_grace_time`; нет межджобового мьютекса. При наложении двух тяжёлых на 1-CPU инстансе + общий пул из 15 соединений — риск исчерпания пула → `pool_timeout=10` → пользовательские sync-роуты падают/висят. Это ровно тот симптом, ради диагностики которого написаны `/debug/connectivity` и `/debug/selftest` (и упомянут в MEMORY «LLM/FRED-кроны вешали БД»).
  - Рекомендация: `AsyncIOScheduler(..., job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})`; развести утренний/вечерний кластеры по времени; поднять `pool_size` или гейтить тяжёлые джобы семафором.
- Дубль роута `@app.get("/")`: объявлен дважды (`main.py:914` и `:965`) — второй перекрывает первый, безобидно, но мусор.

### 7. api/market.py — god-file
1118 строк, **39 роутов**, ~10 несвязанных доменов в одном файле: индексы, pulse/drivers, instruments/candles/sparklines, market-maps (heatmap/valuation по 4 классам), news, overviews (+generate), compare-asset, calendar (+bonds), geopolitics (+region/digest), institutions, geo-map/SVO-history, earnings, corporate-news, health-проверки Anthropic/LLM. Просится разбивка по доменным роутерам (market_quotes, market_maps, market_news, market_geo, market_calendar).

### 8. Дублирование логики между services
- **Чтение `companies/<TICKER>/financials.json`** — независимо в 14 местах (`bond_risk`, `factor_exposures`, `earnings`, `live_multiples`, `moex_bonds`, `market_maps`, `portfolio`, `portfolio_quality_v2`, `screener_scoring`, `report_watch`, `api/bonds`, `api/companies`, `api/market`). Единого лоадера/кэша нет — каждый сам строит путь и парсит JSON. Риск рассогласования путей/нормализации (напр. `_normalize_financials` живёт только в `api/companies.py`, остальные читают сырой JSON). Рекомендация: `services/company_files.py` с единым `load_financials(ticker)`.
- **LLM-вызовы:** есть централизованный `services/llm.py`, но вокруг него у многих сервисов свои обёртки/промпт-склейки (`earnings`, `card_review_agent`, `ai_analysis`, `macro_cb_sync`, `geo_digest`, `geopolitics`, `macro_*`). Терпимо, но стоит вынести общий «complete + retry + budget» хелпер.

### 9. Обработка ошибок и таймауты
- `except: pass` (глотание) — 4 места: `api/market.py:113/129/176`, `api/bonds.py:441` (+ `bonds.py:269` continue). В основном вокруг некритичного обогащения ответа; желательно хотя бы `logger.debug`.
- Массовые `except Exception: # noqa BLE001` в сервисах — с `logger.exception`, это осознанная «не ронять весь джоб из-за одного источника» стратегия (видно в `_macro_job`), приемлемо.
- **httpx-таймауты:** проверены все вызовы `httpx.get/post/Client` — таймаут стоит ВЕЗДЕ (10–30с). `urllib.urlopen` в `debug.py` — `timeout=15`. Хорошо.

### 10. Миграции
- Одна голова: `b2d4f8a1c6e3` (66 ревизий, линейная цепочка, множественных heads нет). Alembic-конфликтов нет.

### 11. Тесты
- 10 файлов в `tests/`: `test_companies`, `test_financials`, `test_macro`, `test_macro_quant`, `test_market`, `test_news`, `test_portfolios`, `test_users`. `conftest.py` поднимает отдельную `TEST_DATABASE_URL`, планировщик под pytest выключен (`main.py:810`) — правильно.
- Пробелов: **нет тестов на auth/безопасность** (JWT, доступ к чужому портфелю, закрытость debug), нет тестов agents/assistant/stress/observer/screener. Покрытие — «счастливый путь» витрины.

### 12. requirements.txt
- Всё запинено, версии свежие и согласованные (fastapi 0.136, sqlalchemy 2.0.41, pydantic 2.13, anthropic 0.100.0). Явно неиспользуемых тяжёлых зависимостей не видно: `numpy`/`shapely`/`pypdf`/`openpyxl` используются (risk_metrics/geo/document_analyst/rosstat). Мелочь: `email-validator` без пина.

---

## Что проверить владельцу вручную (не видно с бою)
1. Задан ли `JWT_SECRET_KEY` в панели Timeweb (C2) — если нет, это самый опасный пункт.
2. Доступны ли `/api/debug/*` реально снаружи для POST (routing открыт; я не дёргал мутирующие) — закрыть в любом случае.
