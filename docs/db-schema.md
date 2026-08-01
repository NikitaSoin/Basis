# Что лежит в базе Basis

> Справочник таблиц боевой базы: что где хранится и как это посмотреть.
> Числа строк — фактические на дату сборки справочника, не оценки: системная
> статистика Postgres врёт (показывала 12 пользователей при реальных 20 и ноль
> дивидендов при 1413).

## Как посмотреть данные

Открыть **`/api/debug/sql-console`** на адресе API, вставить токен из переменной
`DEBUG_API_TOKEN` (настройки приложения на Timeweb) — он запомнится в браузере.

Консоль работает **только на чтение**: транзакция объявлена READ ONLY на стороне
Postgres, поэтому любая запись отклоняется самой базой, а не только проверкой текста
запроса. Испортить данные оттуда нельзя.

### С чего начать

```sql
-- сколько людей зарегистрировано и сколько из них что-то сделали
SELECT count(*) AS всего,
       count(*) FILTER (WHERE is_active) AS активных,
       count(*) FILTER (WHERE subscription_type = 'premium') AS премиум
FROM users;
```

```sql
-- регистрации по дням: есть ли приток вообще
SELECT date(created_at) AS день, count(*) AS человек
FROM users GROUP BY 1 ORDER BY 1 DESC;
```

```sql
-- кто дошёл до портфеля, а кто завёл аккаунт и исчез
SELECT u.id, date(u.created_at) AS регистрация, count(p.id) AS портфелей
FROM users u LEFT JOIN portfolios p ON p.user_id = u.id
GROUP BY 1, 2 ORDER BY 2 DESC;
```

```sql
-- какие бумаги люди реально держат
-- ВНИМАНИЕ: у акций secid пустой, тикер лежит через company_id → companies.
-- secid заполнен только у облигаций, фондов и фьючерсов. coalesce сшивает оба случая.
SELECT coalesce(c.ticker, p.secid) AS бумага,
       p.instrument_type            AS тип,
       count(*)                     AS в_портфелях,
       sum(p.quantity)              AS штук
FROM portfolio_positions p
LEFT JOIN companies c ON c.id = p.company_id
GROUP BY 1, 2 ORDER BY 3 DESC;
```

```sql
-- свежесть цен: когда последний раз обновлялись котировки
SELECT max(date) AS последняя_дата, count(*) AS всего_строк FROM quotes;
```

## Таблицы

### Пользователи и продукт

| Таблица | Строк | Что внутри |
|---|---:|---|
| `users` | 20 | Аккаунты. email, тариф (free/premium), дата регистрации, активен ли. |
| `portfolios` | 15 | Портфели пользователей: чей, название, когда создан. |
| `portfolio_positions` | 33 | Бумаги внутри портфелей: количество, средняя цена. 🔴 У акций тикера тут НЕТ — связь через company_id; поле secid заполнено только у облигаций, фондов, фьючерсов. |
| `portfolio_transactions` | 50 | Сделки внутри портфеля: покупка/продажа, цена, комиссия, дата. |
| `portfolio_diagnoses` | 2 | Сохранённые ИИ-диагнозы портфелей. |
| `screener_saved_filters` | 0 | Сохранённые пользователями фильтры скрининга. |
| `assistant_conversations` | 22 | Диалоги с ИИ-помощником: чей, когда. |
| `assistant_messages` | 58 | Сообщения внутри этих диалогов. |
| `verification_codes` | 0 | Коды подтверждения почты. |

### Рыночные данные

| Таблица | Строк | Что внутри |
|---|---:|---|
| `quotes` | 581 333 | 🔴 ЦЕНЫ АКЦИЙ по дням. Единственный источник цены на платформе. |
| `instrument_history` | 260 727 | История цен облигаций, фондов и фьючерсов по дням. |
| `index_history` | 19 254 | История значений индексов (Мосбиржи, RTS, секторальные). |
| `companies` | 261 | Справочник компаний: тикер, название, сектор, капитализация, число акций. |
| `company_metrics` | 261 | Расчётные метрики по компании: P/E, дивдоходность, справедливая цена, бета, волатильность. |
| `bonds` | 3 281 | Справочник облигаций: купон, погашение, оферта, доходность, рейтинг, оценка риска. |
| `funds` | 104 | Биржевые фонды (БПИФ/ETF): состав, комиссия, ошибка слежения. |
| `futures` | 642 | Фьючерсы: базовый актив, ГО, экспирация. |
| `options` | 2 432 | Опционы (раздел в проработке). |
| `spot_assets` | 6 | Валюта и металлы. |
| `dividends` | 1 413 | История и объявленные дивиденды: тикер, дата отсечки, размер. |
| `company_signals` | 3 207 | Сигналы шины: события по компании, из которых собираются дополнения карточек. |

### Макроэкономика

| Таблица | Строк | Что внутри |
|---|---:|---|
| `macro_indicators` | 69 | Справочник макропоказателей: код, название, единица, источник. |
| `macro_data_points` | 14 526 | 🔴 ЗНАЧЕНИЯ макропоказателей по датам — ставка, инфляция, курсы, ВВП. |
| `macro_forecasts` | 66 | Прогнозы: среднесрочный прогноз ЦБ и другие. |
| `macro_interpretations` | 41 | Тексты-интерпретации показателей (что значит для инвестора). |
| `macro_expert_surveys` | 40 | Опросы аналитиков по ожиданиям. |
| `macro_analytics_docs` | 31 | Аналитические документы макроблока. |
| `macro_verifications` | 132 | Результаты автопроверки качества макроданных (11 проверок). |
| `rate_meetings` | 3 | Заседания ЦБ по ключевой ставке. |
| `market_params` | 4 | Параметры рынка для расчётов (безрисковая ставка и т.п.). |

### Новости, гео, институты

| Таблица | Строк | Что внутри |
|---|---:|---|
| `market_updates` | — | Лента новостей: заголовок, рубрика, важность, затронутые тикеры, разбор влияния. |
| `chronicle_entries` | 4 980 | Постоянная база знаний: важные новости и статьи, размеченные ИИ для агентов. |
| `geo_digest_articles` | 1 399 | Статьи геополитического дайджеста. |
| `geo_blocks` | 6 | Блоки геополитики по компаниям. |
| `geo_strike_events` | 214 | События по инфраструктуре (удары, повреждения). |
| `geo_frontline_snapshot` | 10 | Снимок линии фронта для карт. |
| `geo_frontline_sync` | 1 | Служебная: состояние синхронизации карт. |
| `geo_territorial_claims` | 51 | Территориальные данные для карт. |
| `barometer_versions` | 15 | Версии геополитического и институционального барометров. |
| `situation_overlays` | 11 | Наложения текущей ситуации на карточки. |

### Отчётность и контент карточек

| Таблица | Строк | Что внутри |
|---|---:|---|
| `calendar_events` | 5 172 | Единый календарь: отчёты, дивиденды, оферты, заседания ЦБ, IPO. |
| `earnings_reports` | 380 | Вышедшие отчёты компаний: период, стандарт, ссылка на источник. |
| `earnings_digests` | 368 | Разборы отчётов: главное, плюсы, риски, вывод. |
| `earnings_figures` | 368 | Числа из отчётов, извлечённые для разбора. |
| `interim_financials_overlay` | 24 | Промежуточная отчётность поверх годовой. |
| `card_prose_overlays` | 362 | Обновлённые тексты карточек (авто-свежесть прозы). |
| `agent_addenda` | 40 | Дополнения к карточкам от агентов (под код-гейтом). |
| `observer_reports` | 30 | Отчёты Обозревателя. |
| `company_analyses` | 5 | Аналитические разборы компаний (сейчас пусто). |
| `company_profiles` | 4 | Профили компаний, старая таблица (пусто). |
| `market_overviews` | 4 | Обзоры рынка (пусто). |

### Служебное

| Таблица | Строк | Что внутри |
|---|---:|---|
| `job_heartbeats` | 30 | Пульс фоновых задач: когда какой крон отработал. |
| `alembic_version` | 1 | Служебная: версия схемы БД. |

## Колонки по таблицам

<details><summary>Развернуть полный список полей</summary>

**`agent_addenda`** — id, ticker, kind, status, content, gate_notes, run_trace, model_used, tokens_used, created_at

**`alembic_version`** — version_num

**`assistant_conversations`** — id, user_id, title, created_at, updated_at

**`assistant_messages`** — id, conversation_id, role, content, source_refs, created_at

**`barometer_versions`** — id, kind, source, status, payload, parent_id, trigger_reason, gate_notes, model_used, created_at

**`bonds`** — id, secid, isin, short_name, issuer_name, bond_type, board, currency, face_value, coupon_percent, coupon_value, coupon_period, maturity_date, offer_date, has_amortization, lot_size, listing_level, last_price, ytm, duration_days, accrued_int, risk_tier, spread_bp, updated_at, coupon_type, ytm_kind, is_defaulted, agency_rating, agency_rating_source, issuer_ticker, floater_spread_bp

**`calendar_events`** — id, event_type, event_date, event_time, ticker, sector, title, status, source, source_url, payload, dedup_key, created_at, updated_at

**`card_prose_overlays`** — id, ticker, tab, kind, status, patched_md, original_md, change_note, evidence, gate_notes, source_signal_id, parent_id, model_used, tokens_used, created_at

**`chronicle_entries`** — id, kind, title, summary, interpretation, key_takeaways, tickers, sectors, themes, importance, published_at, event_date, source_key, source_url, source_table, source_id, model_used, created_at

**`companies`** — id, ticker, name, sector, description, created_at, market_cap, paired_ticker, shares_outstanding, historical_tickers

**`company_analyses`** — id, company_id, bull_case, bear_case, risks, fair_price, analyst_note, created_at, business_model, financials, competitors, macro_economy, global_economy, geopolitics, technical_analysis

**`company_metrics`** — id, ticker, sector, pe_current, pe_historical, div_yield, fair_value, beta, volatility, updated_at, return_3y, history_years, beta_moex, beta_calc, beta_source, beta_moex_date, r_squared, r_squared_moex, downside_vol, var_95, earnings_yield, return_total_3y, alpha_3y, sortino_3y, capm_expected, eps_implied, dps_implied

**`company_profiles`** — id, ticker, profile_json, data_quality, completeness_pct, version, created_at, updated_at

**`company_signals`** — id, ticker, signal_type, card_tab, importance, trust, internal, title, summary, source_key, source_url, published_at, dedup_key, consumed_at, created_at

**`dividends`** — id, ticker, record_date, amount, currency

**`earnings_digests`** — id, report_id, headline, one_liner, metrics_snapshot, what_report_showed, what_changed, summary, importance, model_used, created_at, highlights, risks_or_caveats, data_gaps

**`earnings_figures`** — id, report_id, revenue_q, revenue_ttm, ebitda, net_profit_q, net_profit_ttm, adjusted_profit, net_debt, nd_ebitda, dividend_declared, dividend_yield, price, market_cap, pe_ttm, pb, ev_ebitda, is_company_adjusted, segments, prev, extracted_fields

**`earnings_reports`** — id, ticker, period, standard, report_type, published_at, source, source_url, raw_file_ref, status, created_at, calendar_event_id, market_update_id

**`funds`** — id, secid, isin, short_name, sec_name, fund_type, benchmark, currency, listing_level, last_price, val_today, num_trades, ter, updated_at

**`futures`** — id, secid, short_name, sec_name, board, asset_code, asset_name, asset_kind, linked_ticker, expiration_date, min_step, step_price, lot_volume, last_price, settle_price, prev_settle, open_position, initial_margin, contract_value, leverage, updated_at

**`geo_blocks`** — id, region, tab, title, status_text, channels, scenarios, market_impact, affected_sectors, affected_tickers, source_count, model_used, updated_at, created_at

**`geo_digest_articles`** — id, target, title, summary, investor_relevance, published_at, source_url, source_key, model_used, created_at, key_takeaways

**`geo_frontline_snapshot`** — id, theater, snapshot_date, frontline_geojson, control_fill_geojson, as_of, created_at

**`geo_frontline_sync`** — id, theater, frontline_geojson, as_of, source, status, error_note, synced_at, control_fill_geojson, capture_isochrone_geojson, contested_zone_geojson

**`geo_strike_events`** — id, theater, location_name, lat, lon, target_type, significance, label, note, event_date, source_key, source_url, expires_at, created_at

**`geo_territorial_claims`** — id, settlement, oblast, lat, lon, status, note, claimed_date, source_key, source_url, updated_at, created_at

**`index_history`** — id, ticker, date, open, close, high, low, value

**`instrument_history`** — id, asset_class, secid, date, open, close, high, low, value, prev_close, change_pct, yld, accrued_int, settle, oi

**`interim_financials_overlay`** — id, ticker, fiscal_year, start_m, end_m, period_label, period_type, cumulative, standard, end_date, figures, fields_present, source, source_report_id, created_at, updated_at

**`job_heartbeats`** — job_id, last_success, last_error, last_error_text, runs_total, errors_total, updated_at

**`macro_analytics_docs`** — id, source, doc_type, title, summary, key_takeaways, published_at, source_url, model_used, created_at, interpretation

**`macro_data_points`** — id, indicator_code, as_of, metric, value, unit, is_preliminary, source, source_url, ingested_via, revised_at, created_at

**`macro_expert_surveys`** — id, as_of, indicator, year, value, n_respondents, source_url, created_at

**`macro_forecasts`** — id, as_of, scenario, indicator, year, value, comment, source_url, created_at

**`macro_indicators`** — code, title, unit, country, frequency, metric_types, influence_short, influence_full, source_type, display_group, sort_order, sectors

**`macro_interpretations`** — id, sections, generated_at, model_used, source_snapshot

**`macro_verifications`** — id, run_at, check_key, check_type, title, status, message, details, created_at

**`market_overviews`** — id, overview_type, content, period, created_at

**`market_params`** — key, value, as_of, note, updated_at

**`market_updates`** — id, title, content, source, published_at, created_at, source_url, original_title, rubric, importance, summary, impact_comment, affected_tickers, affected_sectors, cluster_id, sources_json, model_used, status, fetched_at, updated_at, category

**`observer_reports`** — id, user_id, report_type, horizon_days, content, source_refs, portfolio_snapshot, model_used, generated_at, topic

**`options`** — id, secid, short_name, option_type, strike, central_strike, expiration_date, underlying, underlying_price, asset_code, asset_name, premium, intrinsic_value, time_value, breakeven, iv, delta, theta_day, vega, updated_at

**`portfolio_diagnoses`** — id, portfolio_id, shield, vulnerabilities, summary, summary_type, portfolio_snapshot, model_used, generated_at

**`portfolio_positions`** — id, portfolio_id, company_id, quantity, avg_buy_price, created_at, instrument_type, secid, currency

**`portfolio_transactions`** — id, position_id, side, quantity, price, fee, trade_date, created_at

**`portfolios`** — id, user_id, name, description, created_at

**`quotes`** — id, company_id, date, open, close, high, low, volume, prev_close, change_abs, change_pct

**`rate_meetings`** — id, decision_date, rate_value, signal, next_meeting_date, consensus_forecast, press_summary, forecast_doc_url, created_at

**`screener_saved_filters`** — id, user_id, asset_class, name, config, created_at

**`situation_overlays`** — id, blocks, generated_at, model_used, source_snapshot, published, blocked_reason

**`spot_assets`** — id, secid, short_name, name, kind, base_code, last_price, prev_close, change_pct, updated_at

**`users`** — id, email, hashed_password, is_active, created_at, subscription_type, subscription_expires_at

**`verification_codes`** — id, channel, destination, purpose, code_hash, attempts, expires_at, created_at

</details>

## Чего в базе НЕТ

Аналитика карточек компаний (финансы, бизнес-модель, управление, макро, гео) лежит
**не в базе, а в файлах**: `backend/companies/<ТИКЕР>/*.json` и `*.md`. В базе — только
рыночные данные, пользователи и то, что собирается автоматически. Поэтому вопросы вроде
«у скольких компаний заполнен блок геополитики» через SQL не решаются — это подсчёт по
файлам.

Поведение пользователей (какие страницы смотрят, сколько времени проводят) в базе тоже
нет — это Яндекс.Метрика, счётчик 111213378.
