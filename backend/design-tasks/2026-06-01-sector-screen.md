# Дизайн-ревью / ТЗ: «Сравнение с сектором»
Дата: 2026-06-01
Источник: новый блок внутри карточки компании (вкладка «Финансы»), данные `/api/sectors/{key}/peers`
Автор: design-critic (senior product designer, финтех)

---

## Что я увидел

В карточке компании уже есть вкладка «Финансы» (`renderFinancials`, `App.js` ~строка 2227),
которая показывает ключевые мультипликаторы текущей компании (P/E, P/S, P/B, EV/EBITDA,
Чистый долг/EBITDA, ROE) чипами + markdown-разбор. В `finJson` уже лежит поле
`relative_peers_sector` (`rel`, строка 2240), но оно сейчас **не отрисовывается**. То есть
секторный контекст для пользователя сегодня отсутствует: он видит «P/E = 9.86», но не понимает,
дорого это или дёшево относительно конкурентов.

Графической библиотеки в проекте нет. Весь фронт — один файл `App.js`, inline-стили +
CSS-переменные, тёмная/светлая тема, иконки `lucide-react`. Значит scatter-карты рисуем
**чистым SVG**.

---

## РЕШЕНИЕ ПО НАВИГАЦИИ (обосновано)

**Выбор: раздел «Сравнение с сектором» ВНУТРИ вкладки «Финансы» карточки компании.
НЕ отдельный секторный экран.**

Почему так, а не отдельный экран:

1. **Контекст пользователя — компания, а не сектор.** Пользователь зашёл в карточку TATN,
   чтобы понять, покупать ли TATN. Вопрос «дорогой ли TATN относительно сектора» — это
   продолжение разбора финансов конкретной бумаги, а не самостоятельная задача «исследовать
   нефтегаз». Прогрессивное раскрытие: сначала мультипликаторы компании, ниже — её положение
   среди конкурентов.
2. **Карты уже «эгоцентричны».** В `points[]` всегда подсвечивается текущая компания
   (`ticker === company.ticker`). Карта без «своей» точки теряет половину смысла. Значит у
   карты всегда есть «хозяин» — это карточка компании.
3. **Минимум новой навигации.** Отдельный экран = новый пункт в `TABS` верхнего уровня
   (`App.js` ~4680/4790), новый роутинг, новый способ выбрать сектор. Это лишняя сущность на
   MVP. Внутри «Финансов» — ноль изменений в навигации.
4. **Данные уже там же.** `finJson.relative_peers_sector` уже привязан к текущей компании и
   уже фетчится в том же `useEffect`. Добавляем один фетч `peers.json` рядом.

**Анти-риск (важно):** не дублируем секторную таблицу в каждой вкладке. Внутри «Финансов»
блок «Сравнение с сектором» идёт **последней секцией**, под мультипликаторами и markdown-разбором,
со своим заголовком-якорем. Это «глубже по скроллу» — то, что нужно не всем.

> На будущее (НЕ в этом ТЗ): когда появится экран «Обозреватель рынка» с drill-down по
> секторам, тот же компонент `<SectorPeers>` переиспользуется там в режиме «без выделенной
> компании» (проп `currentTicker={null}`). Поэтому компонент сразу делаем самодостаточным и
> переиспользуемым.

---

## Что не работает сегодня (приоритизировано)

1. **[КРИТИЧНО] Нет секторного контекста.** Мультипликатор без сравнения с пирами —
   это число без смысла. Инвестор не может оценить «дорого/дёшево» по одной компании.
2. **[ВАЖНО] `relative_peers_sector` собирается, но не показывается.** Данные есть, ценность
   ноль — мёртвый код в `finJson`.
3. **[ВАЖНО] Аномалии не видны.** В данных 22 из 26 компаний помечены `anomaly:true` и
   исключены из медианы. Если показать «средний P/E сектора» без пометки про аномалии —
   пользователь сравнит TATN с мусорной средней. Нужны звёздочка + сноска.

---

## АРХИТЕКТУРА БЛОКА

Раздел «Сравнение с сектором» состоит из трёх частей сверху вниз:

```
┌─ Сравнение с сектором ─────────────────────────────┐
│  Подзаголовок: «Нефть и газ · 26 компаний»          │
│                                                     │
│  ┌── Карта 1 ──────┐   ┌── Карта 2 ──────┐          │  ← две SVG-карты в ряд
│  │ Долг vs Оценка  │   │ Качество vs Цена│          │     (на узком — стопкой)
│  │   [scatter]     │   │   [scatter]     │          │
│  └─────────────────┘   └─────────────────┘          │
│  * — аномалия (мультипликаторы искажены), см. ниже  │  ← сноска
│                                                     │
│  ┌── Таблица сравнения ──────────────────────────┐  │
│  │ Тикер │ P/E │ P/S │ P/B │ EV/E │ ND/E │ ROE   │  │  ← 2025 (2024 серым ниже)
│  │ TATN  │ ... выделена строка текущей компании   │  │
│  │ ...                                            │  │
│  │ Медиана сектора │ ...                          │  │  ← строки-агрегаты
│  │ Среднее сектора │ ...                          │  │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## ДАННЫЕ И ФЕТЧИНГ

### Маппинг сектора → ключ
В компании есть поле `company.sector` (строка типа «Нефть и газ»). API ждёт `sector_key`
(`oil_gas`). Добавляем словарь рядом с уже существующим `SECTOR_ORDER` (App.js ~1357):

```jsx
// App.js — рядом с SECTOR_ORDER
const SECTOR_KEY_BY_NAME = {
  "Нефть и газ": "oil_gas",
  "Финансы": "finance",
  "Металлургия": "metals",
  "IT-сектор": "it",
  "Потребительский сектор": "consumer",
  "Телеком": "telecom",
  "Электроэнергетика": "power",
  "Химия": "chemicals",
  "Девелопмент": "development",
  "Транспорт и логистика": "transport",
  "Здравоохранение": "healthcare",
  "Машиностроение": "machinery",
};
```
> Зависимость: ключи должны совпадать с `sector_key` в бэкенде (`config/sectors.json`).
> Если ключ не найден — блок «Сравнение с сектором» просто не рендерится (graceful).

### Фетч peers
Добавляем в тот же `useEffect`, где грузятся финансы (App.js ~1705–1719). Новое состояние:

```jsx
// рядом с finMd/finJson (App.js ~1640)
const [peersJson, setPeersJson] = useState(null);

// внутри того же useEffect по company.ticker:
useEffect(() => {
  setPeersJson(null);
  const key = SECTOR_KEY_BY_NAME[company.sector];
  if (!key) return;
  fetch(`${apiUrl}/api/sectors/${key}/peers`)
    .then(r => r.ok ? r.json() : null)
    .then(setPeersJson)
    .catch(() => setPeersJson(null));
}, [company.ticker, company.sector]);
```

---

## (А) ПЕРЕИСПОЛЬЗУЕМЫЙ SVG-SCATTER-КОМПОНЕНТ

Один компонент `<ScatterMap>` рисует любую из двух карт. Он сам считает домены min/max,
рисует оси, тики, точки, подписи тикеров, обрабатывает hover через React-state.
Точки с `x===null || y===null` отбрасываются (нет данных). Аномальные — приглушены и
помечены звёздочкой. Текущая компания — крупная, акцентного цвета, всегда поверх остальных.

Разместить **вне** `CompanyDetail` (на верхнем уровне модуля, как и другие хелперы), чтобы
переиспользовать в обозревателе рынка.

```jsx
// ─────────────────────────────────────────────────────────────
// SVG scatter для секторных карт. Без сторонних библиотек.
// props:
//   map           — объект из peers.maps.* (title, x_axis, y_axis, points[])
//   currentTicker — тикер выделяемой компании (или null)
// ─────────────────────────────────────────────────────────────
function ScatterMap({ map, currentTicker }) {
  const [hover, setHover] = useState(null); // {ticker,name,x,y,px,py,anomaly}

  if (!map || !Array.isArray(map.points)) return null;

  // 1. геометрия
  const W = 360, H = 300;
  const padL = 46, padR = 16, padT = 16, padB = 40;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // 2. только точки с данными
  const pts = map.points.filter(p => p.x != null && p.y != null);
  if (pts.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--text-3)", fontSize: 12 }}>
        Недостаточно данных для карты
      </div>
    );
  }

  // 3. домены с запасом 8%
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const pad = (lo, hi) => { const d = (hi - lo) || Math.abs(hi) || 1; return [lo - d * 0.08, hi + d * 0.08]; };
  const [xMin, xMax] = pad(Math.min(...xs), Math.max(...xs));
  const [yMin, yMax] = pad(Math.min(...ys), Math.max(...ys));

  // 4. масштабирование (Y инвертируем — SVG растёт вниз)
  const sx = v => padL + ((v - xMin) / (xMax - xMin)) * plotW;
  const sy = v => padT + (1 - (v - yMin) / (yMax - yMin)) * plotH;

  // 5. «красивые» тики (4 деления по каждой оси)
  const ticks = (lo, hi, n = 4) =>
    Array.from({ length: n + 1 }, (_, i) => lo + ((hi - lo) * i) / n);
  const xTicks = ticks(xMin, xMax);
  const yTicks = ticks(yMin, yMax);
  const fmtTick = v => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));

  return (
    <div style={{ position: "relative" }}>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-1)", marginBottom: 6 }}>
        {map.title}
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        onMouseLeave={() => setHover(null)}
      >
        {/* сетка + тики Y */}
        {yTicks.map((t, i) => (
          <g key={`y${i}`}>
            <line x1={padL} y1={sy(t)} x2={W - padR} y2={sy(t)}
              stroke="var(--border)" strokeWidth="0.5" />
            <text x={padL - 6} y={sy(t) + 3} textAnchor="end"
              fontSize="9" fill="var(--text-3)"
              style={{ fontVariantNumeric: "tabular-nums" }}>{fmtTick(t)}</text>
          </g>
        ))}
        {/* тики X */}
        {xTicks.map((t, i) => (
          <g key={`x${i}`}>
            <line x1={sx(t)} y1={padT} x2={sx(t)} y2={H - padB}
              stroke="var(--border)" strokeWidth="0.5" />
            <text x={sx(t)} y={H - padB + 14} textAnchor="middle"
              fontSize="9" fill="var(--text-3)"
              style={{ fontVariantNumeric: "tabular-nums" }}>{fmtTick(t)}</text>
          </g>
        ))}

        {/* подписи осей */}
        <text x={padL + plotW / 2} y={H - 4} textAnchor="middle"
          fontSize="10" fill="var(--text-2)">{map.x_axis?.label}</text>
        <text x={12} y={padT + plotH / 2} textAnchor="middle"
          fontSize="10" fill="var(--text-2)"
          transform={`rotate(-90 12 ${padT + plotH / 2})`}>{map.y_axis?.label}</text>

        {/* точки: сначала обычные, текущую рисуем последней (поверх) */}
        {pts
          .slice()
          .sort((a, b) => (a.ticker === currentTicker ? 1 : 0) - (b.ticker === currentTicker ? 1 : 0))
          .map(p => {
            const isCur = p.ticker === currentTicker;
            const cx = sx(p.x), cy = sy(p.y);
            const fill = isCur
              ? "var(--accent)"
              : p.anomaly ? "var(--text-3)" : "var(--text-2)";
            const r = isCur ? 6 : 4;
            return (
              <g key={p.ticker}
                onMouseEnter={() => setHover({ ...p, px: cx, py: cy })}
                style={{ cursor: "default" }}>
                {/* невидимая мишень побольше для удобного hover */}
                <circle cx={cx} cy={cy} r={11} fill="transparent" />
                <circle cx={cx} cy={cy} r={r}
                  fill={fill}
                  fillOpacity={isCur ? 1 : p.anomaly ? 0.55 : 0.9}
                  stroke={isCur ? "var(--bg-surface)" : "none"}
                  strokeWidth={isCur ? 1.5 : 0} />
                <text x={cx + r + 3} y={cy + 3}
                  fontSize={isCur ? 10 : 9}
                  fontWeight={isCur ? 600 : 400}
                  fill={isCur ? "var(--accent-text)" : "var(--text-2)"}>
                  {p.ticker}{p.anomaly ? " *" : ""}
                </text>
              </g>
            );
          })}
      </svg>

      {/* tooltip через React-state */}
      {hover && (
        <div style={{
          position: "absolute",
          left: `${(hover.px / W) * 100}%`,
          top: `${(hover.py / H) * 100}%`,
          transform: "translate(8px, -50%)",
          pointerEvents: "none",
          background: "var(--bg-base)",
          border: "1px solid var(--border-mid)",
          borderRadius: 8, padding: "6px 9px",
          fontSize: 11, color: "var(--text-1)",
          whiteSpace: "nowrap", zIndex: 5,
          boxShadow: "0 4px 14px rgba(0,0,0,0.35)",
        }}>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>
            {hover.ticker}{hover.anomaly ? " *" : ""}
          </div>
          <div style={{ color: "var(--text-2)", fontVariantNumeric: "tabular-nums" }}>
            {map.x_axis?.label}: {hover.x?.toFixed(2)}<br />
            {map.y_axis?.label}: {hover.y?.toFixed(2)}
          </div>
        </div>
      )}
    </div>
  );
}
```

Примечания по реализации карт:
- **Карта 1** = `peersJson.maps.map_1_debt_vs_valuation` (X = `net_debt_ebitda`, Y = `ev_ebitda`).
- **Карта 2** = `peersJson.maps.map_2_quality_vs_price` (X = `roe`, Y = `pb`).
- Оси подписаны из `x_axis.label` / `y_axis.label` (уже есть в JSON).
- Звёздочка у точки = `anomaly:true`; единая сноска ниже карт (текст из `anomaly_note`,
  fallback — стандартная фраза, см. ниже).
- Текущая компания узнаётся по `ticker === company.ticker`.
- `bg-base` используется как фон тултипа (отделяется от `bg-surface` карточки).

> Зависимость: задача упоминает поле `anomaly_note`. В текущем `peers.json` его на корневом
> уровне нет (есть массив `anomalies[]` с пер-тикерными `note`). Поэтому: единая сноска под
> картами рендерится из константы (текст ниже), а пер-тикерные `note` показываем опционально
> в тултипе таблицы (если поле появится). Если бэкенд добавит `maps.anomaly_note` — использовать его.

---

## (Б) ТАБЛИЦА СРАВНЕНИЯ

Требования дизайна для таблиц (плотность данных, выравнивание чисел вправо, zebra,
табулярные цифры, заголовки серее):

- 6 мультипликаторов: `pe, ps, pb, ev_ebitda, net_debt_ebitda, roe`.
- Год **2025** — основное (крупно). **2024** — справочно, серым, в той же ячейке мелким под числом.
- Числа выровнены **вправо**, `font-variant-numeric: tabular-nums`.
- Строка текущей компании — выделена `--accent-fade` + `border-left` акцентный.
- Аномальные тикеры — со звёздочкой, приглушённый текст (`--text-3`).
- Внизу две строки-агрегата: **Медиана сектора** и **Среднее сектора** (из
  `sector_aggregates[year]`), визуально отделены верхней границей и моноширинным жирным.
- `null` → «—» (`--text-3`), не «0».
- Длинный список (26 строк) — по умолчанию показываем непустые/неаномальные + текущую,
  остальное под «Показать все 26 →» (паттерн прогрессивного раскрытия из чек-листа).

```jsx
// ─── внутри renderFinancials(), отдельная секция ───
const renderSectorComparison = () => {
  if (!peersJson) return null;
  const ct = peersJson.comparison_table;
  const aggs = peersJson.sector_aggregates || {};
  const rows = ct?.rows || [];
  if (!rows.length) return null;

  const METRICS = [
    { key: "pe", label: "P/E" },
    { key: "ps", label: "P/S" },
    { key: "pb", label: "P/B" },
    { key: "ev_ebitda", label: "EV/EBITDA" },
    { key: "net_debt_ebitda", label: "ND/EBITDA" },
    { key: "roe", label: "ROE" },
  ];
  const num = (v, suff = "") => (typeof v === "number" ? v.toFixed(2) + suff : "—");

  // сортировка: текущая первой, затем не-аномальные, затем аномальные
  const ordered = rows.slice().sort((a, b) => {
    const cur = (r) => (r.ticker === company.ticker ? 0 : 1);
    const an  = (r) => (r.anomaly ? 1 : 0);
    return cur(a) - cur(b) || an(a) - an(b) || a.ticker.localeCompare(b.ticker);
  });
  const [showAll, setShowAll] = useState(false); // ← вынести в state компонента, не в рендер-функцию!
  const visible = showAll ? ordered : ordered.filter(r => !r.anomaly || r.ticker === company.ticker);

  const thBase = {
    textAlign: "right", padding: "7px 10px", fontSize: 11, fontWeight: 500,
    color: "var(--text-3)", borderBottom: "1px solid var(--border-mid)",
    whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums",
  };
  const tdNum = (muted) => ({
    textAlign: "right", padding: "7px 10px", fontSize: 12.5,
    fontFamily: "monospace", fontVariantNumeric: "tabular-nums",
    color: muted ? "var(--text-3)" : "var(--text-1)", whiteSpace: "nowrap",
  });

  const AggRow = ({ title, agg }) => (
    <tr style={{ borderTop: "1px solid var(--border-mid)", background: "var(--bg-base)" }}>
      <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 600, color: "var(--text-2)", position: "sticky", left: 0, background: "var(--bg-base)" }}>{title}</td>
      {METRICS.map(m => (
        <td key={m.key} style={{ ...tdNum(false), fontWeight: 600, color: "var(--text-2)" }}>
          {num(agg?.[m.key], m.key === "roe" ? "%" : "")}
        </td>
      ))}
    </tr>
  );

  return (
    <div style={{ background: "var(--bg-surface)", borderRadius: 12, padding: 18, border: "1px solid var(--border)" }}>
      {/* заголовок секции */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Users size={16} style={{ color: "var(--accent)" }} />
        <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-1)", margin: 0 }}>
          Сравнение с сектором
        </h4>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 14 }}>
        {peersJson.meta?.sector} · {peersJson.meta?.n} компаний · мультипликаторы 2025
        <span style={{ color: "var(--text-3)" }}> (мелким — 2024)</span>
      </div>

      {/* две карты */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: 18, marginBottom: 12,
      }}>
        <ScatterMap map={peersJson.maps?.map_1_debt_vs_valuation} currentTicker={company.ticker} />
        <ScatterMap map={peersJson.maps?.map_2_quality_vs_price} currentTicker={company.ticker} />
      </div>

      {/* сноска про аномалии */}
      <div style={{ fontSize: 11.5, lineHeight: 1.5, color: "var(--text-3)", marginBottom: 18, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
        <b style={{ color: "var(--text-2)" }}>*</b> — мультипликаторы искажены
        (внутригрупповые операции, разовые статьи, низкий free-float, регулируемый тариф и т.п.).
        Такие компании исключены из расчёта медианы и среднего по сектору. Сравнивать с ними
        напрямую некорректно.
      </div>

      {/* таблица */}
      <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid var(--border)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
          <thead style={{ background: "var(--bg-base)" }}>
            <tr>
              <th style={{ ...thBase, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-base)" }}>Тикер</th>
              {METRICS.map(m => <th key={m.key} style={thBase}>{m.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => {
              const isCur = r.ticker === company.ticker;
              const d25 = r["2025"] || {}, d24 = r["2024"] || {};
              return (
                <tr key={r.ticker} style={{
                  background: isCur ? "var(--accent-fade)" : (i % 2 ? "transparent" : "rgba(255,255,255,0.015)"),
                  borderLeft: isCur ? "3px solid var(--accent)" : "3px solid transparent",
                }}>
                  <td style={{
                    padding: "7px 10px", fontSize: 12.5, whiteSpace: "nowrap",
                    fontWeight: isCur ? 600 : 400,
                    color: r.anomaly ? "var(--text-3)" : (isCur ? "var(--accent-text)" : "var(--text-1)"),
                    position: "sticky", left: 0,
                    background: isCur ? "var(--accent-fade)" : "var(--bg-surface)",
                  }}>
                    {r.ticker}{r.anomaly ? " *" : ""}{r.is_pref ? <span style={{ color: "var(--text-3)", fontSize: 10 }}> ап</span> : null}
                  </td>
                  {METRICS.map(m => {
                    const v25 = d25[m.key], v24 = d24[m.key];
                    return (
                      <td key={m.key} style={tdNum(r.anomaly && !isCur)}>
                        <div>{num(v25, m.key === "roe" ? "%" : "")}</div>
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 1 }}>
                          {num(v24, m.key === "roe" ? "%" : "")}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <AggRow title="Медиана сектора" agg={aggs["2025"]?.median} />
            <AggRow title="Среднее сектора" agg={aggs["2025"]?.mean} />
          </tfoot>
        </table>
      </div>

      {ordered.length > visible.length && (
        <button onClick={() => setShowAll(true)} style={{
          marginTop: 10, background: "transparent", border: "none",
          color: "var(--accent-text)", fontSize: 12.5, fontWeight: 600,
          cursor: "pointer", padding: "4px 0",
        }}>
          Показать все {ordered.length} компаний →
        </button>
      )}
      {aggs.note && (
        <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 10, lineHeight: 1.5 }}>
          {aggs.note}
        </div>
      )}
    </div>
  );
};
```

> ВАЖНО по React-правилам: `useState(showAll)` нельзя объявлять внутри вложенной
> функции `renderSectorComparison`. Подними `const [peersShowAll, setPeersShowAll] = useState(false)`
> на уровень компонента `CompanyDetail` (рядом с `tab`), а в функции только используй.
> То же касается `hover` — он внутри `<ScatterMap>` (это полноценный компонент), там можно.

### Куда вставить
В `renderFinancials()`, в финальный JSX, **последним** дочерним элементом враппера
`<div style={{ display: "flex", flexDirection: "column", gap: 16 }}>` (App.js ~2285–2286),
после markdown-разбора:

```jsx
return (
  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
    {/* ...существующие чипы мультипликаторов... */}
    {/* ...существующий markdown-разбор... */}
    {renderSectorComparison()}   {/* ← НОВОЕ, последним */}
  </div>
);
```

Иконку `Users` добавить в импорт из `lucide-react` (вверху App.js), если её ещё нет.

---

## Цветовое кодирование (смысл, не украшение)

| Элемент | Цвет | Смысл |
|---|---|---|
| Точка/строка текущей компании | `--accent` / `--accent-fade` | «вот ты здесь» |
| Обычная компания (точка) | `--text-2`, opacity 0.9 | пир, сопоставим |
| Аномальная компания | `--text-3`, opacity 0.55 + `*` | данные искажены, осторожно |
| Строки агрегатов | фон `--bg-base`, текст `--text-2` bold | ориентир сектора |
| Оси/сетка | `--border` 0.5px | фон, не отвлекает |
| Подписи осей | `--text-2` | читаемо, второстепенно |

Намеренно **не** красим P/E зелёным/красным: «низкий P/E» не равно «хорошо» (см. аномалии —
у мусорных компаний P/E самый низкий). Цвет тут — про статус компании (своя/пир/аномалия),
а не про знак числа. Это сознательное решение против ложного сигнала.

---

## Адаптивность
- Карты: `grid` с `auto-fit minmax(280px,1fr)` — на широком два столбца, на узком стопкой.
- SVG масштабируется через `viewBox` + `width:100%` (числовые координаты остаются стабильными).
- Таблица: `overflow-x:auto`, `min-width:560px`, первая колонка `position:sticky;left:0`.

---

## Чего НЕ менять (важно)
- Существующие чипы мультипликаторов и markdown-разбор в «Финансах» — оставить как есть,
  новый блок идёт под ними.
- Структуру `TABS` карточки и верхнюю навигацию — не трогаем (это весь смысл выбора навигации).
- CSS-переменные — используем только существующие (`--accent`, `--accent-fade`, `--accent-text`,
  `--text-1/2/3`, `--bg-surface`, `--bg-base`, `--border`, `--border-mid`). Новых не вводим.
- Не подключаем recharts/d3/любую графику — только нативный SVG.

---

## Зависимости (для бэкенда/данных)
1. Эндпоинт `GET /api/sectors/{key}/peers` должен отдавать структуру как в
   `sectors/oil_gas/peers.json` (есть `comparison_table.rows`, `sector_aggregates`, `maps.*`).
2. Ключи секторов в `SECTOR_KEY_BY_NAME` должны совпасть с `config/sectors.json`.
   На сейчас точно есть только `oil_gas` — остальные карты появятся по мере генерации peers
   для других секторов; до этого блок просто не рендерится (graceful, без ошибок).
3. (Опционально) `maps.anomaly_note` — единый текст сноски с бэкенда; пока используется
   константа во фронте.

---

## Оценка трудозатрат
**M (полдня).**
- `<ScatterMap>` (новый компонент): ~1.5 ч.
- `renderSectorComparison` + таблица: ~1.5 ч.
- Фетч peers, маппинг сектора, состояние, вставка: ~1 ч.
- Визуальная отладка доменов/тиков/тултипа на реальных данных oil_gas: ~1 ч.
