# Дизайн-ревью: раздел «Стресс-тестирование» (верхняя навигация, демо-версия сценарного анализа)

Дата: 2026-07-22
Источник: inbasis.ru → Стресс-тестирование (НЕ путать с внутрипортфельным стресс-тестом
Портфеля — `app/api/portfolios/{id}/stress-test`). Код: `frontend/Basis/src/portfolio/StressTestView.jsx`
(326 строк). Бэкенд: `backend/app/api/stress_scenarios.py` (роутер, 3 эндпоинта +
1 неиспользуемый), `backend/app/services/stress_numeric.py` (числовой контур),
`backend/app/services/stress_scenarios.py` (сценарный движок + 6 пресетов).

## Что я увидел

Экран сделан по схеме «спроси свободным текстом ИЛИ задай точные уровни ставки/курса/
нефти» → получи (1) как ИИ понял вопрос, (2) текстовый разбор эксперта по секторам и
компаниям, (3) таблицу Δ выручка/EBITDA/чистая прибыль по компаниям, (4) для
качественных факторов — направление по бакетам ▲▲/▲/─/▼/▼▼. Демо честно
промаркировано баннером сверху. Проблема не в объёме проделанной работы (бэкенд
движок содержательный, есть даже собственная эпистемическая оговорка в docstring
`stress_scenarios.py:8-28`), а в том, что **экран рендерит вывод модели буквально
как он приходит из API** — без сигнального слоя, почти без визуального
ранжирования и почти без эпистемических меток на фронте, хотя все нужные для этого
кирпичи (компоненты `Delta`, `Table`, `ImpactBar`, `Treemap`, CSS-классы
`.bs-tag-*`/`.bs-wind-*`/`.bs-chip-stat`) уже существуют в кодовой базе и просто не
используются здесь.

Проверка по «4 слоям чтения» (конституция, раздел 🎨 ДИЗАЙН) — экран пофакту:

| Слой | Что требует конституция | Что есть на экране сейчас |
|---|---|---|
| 1. Идентичность | что это за объект | заголовок сценария («Как мы поняли...») — есть, ок |
| 2. Сигнал | одно главное число/вердикт | **отсутствует.** Нет ни одной фразы/цифры вида «сильнее всего пострадает Х», нет саммари-карточки над таблицей |
| 3. Доказательство/надёжность | таблица + степень уверенности | таблица есть (`NumericTable`, `StressTestView.jsx:43-84`), но БЕЗ ранжирования и БЕЗ явной метки уровня достоверности рядом с числами |
| 4. Действие | что со мной сделать | нет (уместно — раздел не про «купи/продай», но сравнение с портфелем/отслеживание тоже не предложено) |

Слой 2 отсутствует буквально — это подтверждает придирку из задания: **таблица
`NumericTable` (скриншот `stress_06_lower.png`) — ровно тот случай, который
конституция называет НЕ готовым экраном** («вердикт поверх данных» дословно).

## Что не работает (приоритизировано)

1. **[КРИТИЧНО]** Нет сигнального слоя над таблицей чисел — прямое нарушение
   конституции («голая таблица без интерпретации не считается готовым экраном»).
   `NumericTable` (`StressTestView.jsx:43-84`) рендерит заголовок карточки → сразу
   `<table>` на все компании. Пользователь должен сам построчно просканировать
   до 20 строк (`.slice(0,20)`, строка 45), чтобы понять, кому хуже всего — притом
   что это именно первый вопрос, который задаёт себе человек про сценарий «нефть
   $45» (скриншот `stress_06_lower.png`).

2. **[КРИТИЧНО]** Сортировка таблицы физически прячет самую пострадавшую компанию
   в конец списка — это не только UI-проблема, а конкретный баг бэкенда:
   `backend/app/services/stress_numeric.py:170-178` —
   ```python
   np_pct = (impact["metrics"].get("net_profit") or {}).get("pct_of_base")
   companies.append({..., "_sort": abs(np_pct) if np_pct is not None else -1})
   companies.sort(key=lambda c: (not c["is_blue_chip"], -c["_sort"]))
   ```
   `pct_of_base` намеренно гасится в None, когда `|Δ| > 2×|базы|` (см.
   `stress_numeric.py:134-137`, оговорка «у OZON прибыль ~1 млрд → "+543%" ничего не
   говорит» — сама по себе разумная защита). Но именно ПОЭТОМУ у Роснефти в
   сценарии «нефть $45» `pct_of_base` гасится (эффект больше базы), `_sort`
   становится `-1` — и Роснефть с Δ чистой прибыли **−680,9 млрд ₽ (самый большой
   абсолютный удар среди голубых фишек в этом сценарии)** сортируется **последней**
   среди 6 голубых фишек в таблице (проверено на скриншоте `stress_06_lower.png`:
   порядок TATN → NVTK → GAZP → LKOH → SNGS → ROSN, хотя по |Δ млрд| порядок должен
   быть ROSN → GAZP → LKOH → TATN → SNGS → NVTK). Ровно то самое «какая компания
   пострадает БОЛЬШЕ всех — не считывается за секунду», о чём просили проверить, —
   и причина не только в отсутствии визуализации, а в том, что порядок строк
   активно вводит в заблуждение.

3. **[КРИТИЧНО]** Дельты без глифа ▲/▼ — прямое нарушение зафиксированной
   конвенции («дельты — глиф ▲/▼ у дельт»). `DeltaCell` (`StressTestView.jsx:30-41`)
   рендерит только цвет + знак числа:
   ```jsx
   <span className={`tw-font-mono tw-tabular-nums ${positive ? "tw-text-success" : "tw-text-danger"}`}>
     {fmtBn(m.delta_bn)} <span className="tw-text-[10.5px]">млрд</span>
     ...
   ```
   Никакого `▲`/`▼` нет — видно на `stress_06_lower.png`, все числа просто красные.
   При этом в `frontend/Basis/src/design/primitives.jsx:594-611` уже есть готовый
   компонент `Delta`, который именно так и сделан (глиф + семантический цвет +
   `tw-tabular-nums`) — компонент не импортирован в `StressTestView.jsx` (сейчас
   импортируются только `Card, Badge`, строка 3).

4. **[КРИТИЧНО]** Таблица дублирует и путает эмитентов через обычка/префы —
   подрывает доверие к самим числам. В `stress_06_lower.png` видно: TATN и TATNP
   (Татнефть), MFGS и MFGSP (Славнефть), BANE и BANEP (Башнефть) — пары строк с
   **идентичными** цифрами (то есть чистый визуальный шум, задваивающий список без
   новой информации), но SNGS и SNGSP (Сургутнефтегаз) — пары строк с **разными**
   цифрами для Δ выручки (SNGS: −721 млрд/−28,2%; SNGSP: −599,2 млрд/−23,5%) для
   ОДНОЙ и той же компании. Это уже не оформление, а сигнал недоверия к данным —
   пользователь, заметивший расхождение, усомнится во всей таблице. Пары к тому же
   не стоят рядом в списке (TATN — 1-я строка, TATNP — 14-я), то есть дубликат
   даже не считывается как дубликат, а выглядит как ещё одна пострадавшая компания.

5. **[ВАЖНО]** Шрифты экрана — легаси, явно запрещённое конституцией. Весь экран
   держится на `design/primitives.jsx`/`tailwind.config.js` (Tailwind-утилиты с
   префиксом `tw-`), где:
   ```js
   // tailwind.config.js:73-75
   sans: ["Inter", ...],
   display: ["Inter Display", "Inter", ...],
   mono: ["JetBrains Mono", ...],
   ```
   `tw-font-mono` (все числа, все тикеры, инпуты — `StressTestView.jsx` строки 34,
   63, 104, 150, 266/271/276) → **JetBrains Mono**. `tw-font-display` (заголовок
   «Стресс-тестирование», `StressTestView.jsx:230`) → **Inter Display**. Оба шрифта
   дословно названы устаревшими в конституции («JetBrains Mono / Source Serif 4 —
   СТАРЫЕ, НЕ использовать»); канон — Fraunces (serif-заголовки) и IBM Plex Mono
   (числа). Оба нужных шрифта УЖЕ подключены в `public/index.html:47-49` — то есть
   это чисто вопрос переключения CSS-класса, не загрузки нового ресурса.

6. **[ВАЖНО]** Эпистемических меток на экране почти нет, кроме одного баннера
   сверху. Единственная метка внутри результата — серый текст 11.5px в самом низу
   огромной карточки `ExpertBlock`: `{e.kb_note}` («Ответ построен ИИ... —
   суждение, не расчёт», `StressTestView.jsx:132`) — после десятков строк текста
   (см. `stress_06_lower.png`, самый низ карточки «Разбор эксперта»), легко не
   заметить вообще. У таблицы чисел (`NumericTable`, это МОДЕЛЬНЫЙ расчёт по
   коэффициентам чувствительности) нет метки уровня рядом с заголовком — только
   методологическая сноска внизу (строка 81, тоже 11.5px). При этом в
   `frontend/Basis/src/styles/basis-design-system.css:94-97` уже готовы классы
   `.bs-tag-fact`/`.bs-tag-estimate`/`.bs-tag-judgment` именно под три уровня
   достоверности продукта — файл подключён глобально
   (`frontend/Basis/src/index.js:5`), их можно использовать без импорта, просто
   как className.

7. **[ВАЖНО]** «Разбор эксперта» — стена единообразного текста без ранжирования
   по значимости, ровно как описано в задании. `ExpertBlock` (`StressTestView.jsx:88-135`),
   компонент `Side` (строки 89-111): каждый сектор — жирное имя + серая пометка
   силы («слабо»/«заметно»/«сильно», из `STRENGTH`, строка 86) + абзац; каждая
   компания — жирный моноширинный тикер + тире + абзац. Визуально ВСЕ записи
   одинаковы независимо от `strength` (1/2/3) — сила эффекта закодирована только
   словом мелким серым шрифтом, не цветом/интенсивностью/порядком. Заголовки
   колонок «Потенциальные бенефициары»/«Потенциально под давлением» цветные
   (`tw-text-success`/`tw-text-danger`, строка 91), но сам список строк внутри —
   монохромный текст, то есть цветовой сигнал есть только у заголовка и теряется
   именно там, где он нужнее всего (по строкам). Наглядно на `stress_03_result_final.png`
   → `stress_06_lower.png`: колонка «под давлением» — 4 сектора + 6 компаний одним
   сплошным перечислением, ни одного визуального якоря, кроме жирности тикера.

8. **[ВАЖНО]** Пустое состояние заметно беднее остального сайта и не использует
   уже готовую бэкенд-функциональность. На `stress_01.png` (1440×990) контент
   заканчивается на ~648px («Или задайте уровни точно») — ниже **~340px (треть
   видимой области) абсолютно пустого кремового фона**, без футера, без «как это
   работает», без превью примера. При этом бэкенд уже содержит:
   - `GET /api/stress-test/scenarios` (`backend/app/api/stress_scenarios.py:12-15`)
     — список из 6 кураторских пресетов (`backend/app/services/stress_scenarios.py:50-83`:
     «Война ещё 4 года», «Обвал цены нефти», «Ближний Восток: нефть резко
     дорожает», «Рост налогового/регуляторного давления», «Инфляционные ожидания
     остаются повышенными», «Оптимистичный сценарий Банка России») — с готовыми
     `label`+`description`.
   - `GET /api/stress-test/impact?scenario=<key>` (`stress_scenarios.py:18-26`) —
     детерминированный расчёт (без LLM, без риска «неточно поняли вопрос», без
     задержки на интерпретацию), формат ответа (`winners`/`losers`/`sectors`/
     `total_companies`/`companies_with_signal`) **совпадает 1:1** с тем, что уже
     потребляет существующий `QualTable` (`StressTestView.jsx:137-171`, читает
     `qual.winners`/`qual.losers`/`r.reaction_pct`/`qual.companies_with_signal`/
     `qual.total_companies`).
   Ни один из двух эндпоинтов не вызывается фронтом ни разу — используются
   только `/ask` (LLM) и `/numeric` (3 ручных поля). То есть пустое место внизу
   пустого состояния можно заполнить готовой, надёжной (не LLM) функциональностью
   почти без нового кода на рендер — см. Правку 7.

9. **[ВАЖНО]** Компоненты-заготовки для сигнального слоя уже есть в кодовой базе
   и не используются на этом экране: `ImpactBar` (`frontend/Basis/src/design/PortfolioViz.jsx:309-334`,
   комментарий в коде буквально «signed stress-impact bar (centre origin) —
   value is a signed % (negative = loss)») и `Treemap` (`PortfolioViz.jsx:258-304`,
   размер+цвет плитки по величине эффекта) — оба сделаны под ровно эту задачу
   (видимо для внутрипортфельного стресс-теста), но не импортированы в
   `StressTestView.jsx`. Переиспользование дешевле нового компонента.

10. **[НИЖЕ ПРИОРИТЕТ]** Бакеты качественного направления (`▲▲/▲/─/▼/▼▼`,
    `StressTestView.jsx:12-22`) переизобретают цветовую пилюлю заново
    (`tw-text-success`/`tw-text-danger` голым текстом, строка 153), хотя в каноне
    уже есть готовый `.bs-wind-tag`/`.bs-wind-up`/`.bs-wind-down`/`.bs-wind-neutral`
    (`basis-design-system.css:99-103`) — рассчитан именно на «встречный/попутный
    фактор».

11. **[НИЖЕ ПРИОРИТЕТ]** Бейдж голубой фишки «ГФ» (`Badge tone="accent"`,
    `StressTestView.jsx:62`) красится акцентным медным цветом. По конституции
    акцент («--bs-copper») зарезервирован за кликабельными/CTA-элементами, а «ГФ»
    — это фактологическая классификация (компания входит в индекс голубых фишек),
    т.е. по смыслу ближе к `.bs-tag-fact` (нейтральный серый), не к акценту.

12. **[НИЖЕ ПРИОРИТЕТ]** Таблица `NumericTable` — самодельный `<table>`
    (строки 48-74) вместо уже существующего `Table` из `design/primitives.jsx:613-664`
    (тот же принцип: числа справа, `tw-tabular-nums`, ховер строки), который к тому
    же сразу принял бы `Delta` из Правки 3 через `column.render`.

13. **[НИЖЕ ПРИОРИТЕТ]** Два предупреждения визуально неразличимы по серьёзности:
    постоянный демо-дисклеймер сверху (`StressTestView.jsx:218-227`,
    `tw-bg-warning-soft`) и ситуативные `out_of_scope`/`no_signal` врезки
    (строки 306-311) используют одинаковый жёлтый бокс — не разделены «это правда
    всегда» vs «в этом конкретном ответе что-то не так».

14. **[НИЖЕ ПРИОРИТЕТ]** Enter в поле «Спросите сценарий» отправляет запрос
    (`onKeyDown`, строка 242), а поля «Или задайте уровни точно» (rate/rub/oil,
    строки 264-277) не реагируют на Enter — нужно тянуться к кнопке «Посчитать»
    мышью. Небольшая, но заметная асимметрия между двумя одинаковыми по важности
    сценариями ввода на одном экране.

## Что предлагаю (конкретно)

### Правка 1: сигнальный слой над `NumericTable` — карточка-лидерборд

Добавить компонент `ImpactSignal`, который рендерится ПЕРЕД `NumericTable`
(и в ветке `askResult.numeric`, и в ветке `numResult`) и отвечает на вопрос
«кому хуже/лучше всех» одним взглядом, переиспользуя уже готовый `ImpactBar`.

Что менять — импорт (`StressTestView.jsx:3`):
```jsx
import { Card, Badge, Delta } from "../design/primitives";
import { ImpactBar } from "../design/PortfolioViz";
```

Новый компонент (вставить перед `NumericTable`, ~строка 43):
```jsx
function rankByImpact(companies, metric = "net_profit") {
  return companies
    .filter((c) => c.metrics?.[metric]?.delta_bn != null)
    .sort((a, b) => Math.abs(b.metrics[metric].delta_bn) - Math.abs(a.metrics[metric].delta_bn));
}

function ImpactSignal({ numeric }) {
  const ranked = rankByImpact(numeric.companies, "net_profit");
  if (!ranked.length) return null;
  const worst = ranked.filter((c) => c.metrics.net_profit.delta_bn < 0).slice(0, 5);
  const best = ranked.filter((c) => c.metrics.net_profit.delta_bn > 0).slice(0, 5);
  const maxAbs = Math.max(1, ...ranked.slice(0, 8).map((c) => Math.abs(c.metrics.net_profit.delta_bn)));
  const Row = ({ c }) => (
    <div key={c.ticker} className="tw-flex tw-items-center tw-gap-3 tw-py-1">
      <span className="tw-font-mono tw-text-[12px] tw-text-text-secondary tw-w-16 tw-shrink-0">{c.ticker}</span>
      <div className="tw-flex-1"><ImpactBar value={c.metrics.net_profit.delta_bn} max={maxAbs} /></div>
      <Delta value={c.metrics.net_profit.delta_bn} suffix="млрд ₽" className="tw-w-28 tw-justify-end" />
    </div>
  );
  return (
    <Card header={<span className="tw-flex tw-items-center tw-gap-2">Кто пострадает сильнее всего <span className="bs-tag-estimate">оценка</span></span>}>
      <div className="tw-flex tw-flex-wrap tw-gap-3 tw-mb-4">
        <div className="bs-chip-stat">
          <span className="bs-cs-lbl">Задет фактором</span>
          <span className="bs-cs-val">{ranked.length} из {numeric.companies.length}</span>
        </div>
        {worst[0] && (
          <div className="bs-chip-stat">
            <span className="bs-cs-lbl">Хуже всего</span>
            <span className="bs-cs-val" style={{ color: "var(--bs-down)" }}>
              {worst[0].ticker} · {worst[0].metrics.net_profit.pct_of_base != null ? `${worst[0].metrics.net_profit.pct_of_base}%` : `${worst[0].metrics.net_profit.delta_bn} млрд ₽`}
            </span>
          </div>
        )}
      </div>
      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-x-8">
        <div>{worst.map((c) => <Row key={c.ticker} c={c} />)}</div>
        <div>{best.map((c) => <Row key={c.ticker} c={c} />)}</div>
      </div>
    </Card>
  );
}
```
Подключить перед таблицей:
```jsx
{askResult.numeric && <><ImpactSignal numeric={askResult.numeric} /><NumericTable numeric={askResult.numeric} /></>}
...
{numResult && !numLoading && !numResult.error && <><ImpactSignal numeric={numResult} /><NumericTable numeric={numResult} /></>}
```
Альтернативы (если владелец захочет другой вид сигнального слоя — тоже дёшево,
готовые кирпичи есть):
- Три `KpiTile` в ряд («Задето компаний», «Худший результат», «Лучший результат»)
  — `design/primitives.jsx:720-750`, без спарклайна (истории цены здесь нет —
  **зависимость**, если понадобится динамика во времени).
- `Treemap` (`PortfolioViz.jsx:258-304`) на всю вселенную компаний сценария —
  даёт мгновенное «в основном всё красное, самое тёмное — Роснефть» одним
  взглядом ДО таблицы; дороже по интеграции (нужно посчитать `weight`, которого
  здесь физически нет — можно взять равным для всех тайлов).

### Правка 2: чинит первопричину «кто пострадал больше всех — не считывается»

Бэкенд, `backend/app/services/stress_numeric.py:170-178`:
```python
# было
np_pct = (impact["metrics"].get("net_profit") or {}).get("pct_of_base")
companies.append({
    "ticker": ticker, "name": name, "sector": sector,
    "is_blue_chip": ticker in BLUE_CHIPS,
    **impact,
    "_sort": abs(np_pct) if np_pct is not None else -1,
})

# стало
np_metric = impact["metrics"].get("net_profit") or {}
np_pct, np_bn = np_metric.get("pct_of_base"), np_metric.get("delta_bn")
if np_pct is not None:
    sort_key = abs(np_pct)
elif np_bn is not None:
    # % подавлен НЕ потому что эффекта нет, а потому что эффект БОЛЬШЕ базы —
    # это экстремальный случай, ранжируем его высоко, а не последним (было -1,
    # из-за чего Роснефть с крупнейшим |Δ млрд ₽| в сценарии «нефть $45» уходила
    # в конец списка голубых фишек — прямая причина «непонятно кто пострадал больше»).
    sort_key = 999 + abs(np_bn)
else:
    sort_key = -1
companies.append({
    "ticker": ticker, "name": name, "sector": sector,
    "is_blue_chip": ticker in BLUE_CHIPS,
    **impact,
    "_sort": sort_key,
})
```
Группировка «голубые фишки первыми» (`companies.sort(key=lambda c: (not c["is_blue_chip"], -c["_sort"]))`,
строка 178) — сознательное продуктовое решение (см. комментарий в шапке
`StressTestView.jsx:9` — «владелец: голубые фишки первыми»), её НЕ трогаем, чиним
только ранжирование ВНУТРИ группы.

### Правка 3: глиф ▲/▼ на дельтах — переиспользовать `Delta`

`StressTestView.jsx:30-41`:
```jsx
// было
function DeltaCell({ m }) {
  if (!m || m.delta_bn == null) return <span className="tw-text-text-tertiary">—</span>;
  const positive = m.delta_bn >= 0;
  return (
    <span className={`tw-font-mono tw-tabular-nums ${positive ? "tw-text-success" : "tw-text-danger"}`}>
      {fmtBn(m.delta_bn)} <span className="tw-text-[10.5px]">млрд</span>
      {m.pct_of_base != null && (
        <span className="tw-text-[11px] tw-text-text-tertiary tw-ml-1">({positive ? "+" : ""}{m.pct_of_base}%)</span>
      )}
    </span>
  );
}

// стало (Delta уже импортирован Правкой 1)
function DeltaCell({ m }) {
  if (!m || m.delta_bn == null) return <span className="tw-text-text-tertiary">—</span>;
  return (
    <span className="tw-inline-flex tw-items-baseline tw-gap-1.5">
      <Delta value={m.delta_bn} suffix="млрд ₽" decimals={1} />
      {m.pct_of_base != null && (
        <span className="tw-text-[11px] tw-text-text-tertiary">
          ({m.pct_of_base > 0 ? "+" : ""}{m.pct_of_base}%)
        </span>
      )}
    </span>
  );
}
```
`fmtBn` (строки 24-28) после этого не используется нигде и удаляется.

### Правка 4: убрать визуальный шум от обычка/префов в таблице

Минимум (быстро, в объёме фронта): группировать строки одного эмитента визуально.
В `NumericTable` (`StressTestView.jsx:43-84`) перед рендером схлопнуть тикеры с
одинаковым `name` (без суффиксов "им. ...", "-P") в одну строку с пометкой
дополнительных тикеров:
```jsx
function dedupeByIssuer(companies) {
  const seen = new Map();
  for (const c of companies) {
    const key = c.name.replace(/\s*(?:ПАО|АО|"|им\.\s*[\wа-яё.\s]+)\s*$/gi, "").trim();
    if (!seen.has(key)) seen.set(key, { ...c, _also: [] });
    else seen.get(key)._also.push(c.ticker);
  }
  return [...seen.values()];
}
```
и рядом с тикером — `{c._also.length > 0 && <span className="tw-text-[10px] tw-text-text-tertiary tw-ml-1">= {c._also.join(", ")}</span>}`.
**Внимание:** это НЕ решает случай SNGS/SNGSP (разные числа у одной компании) —
это отдельный вопрос к данным/бэкенду (почему коэффициенты чувствительности
common/preferred разошлись), не в объёме этого дизайн-ТЗ, но обязательно зафиксировать
отдельным тикетом аналитику — со схлопыванием строк расхождение станет ЕЩЁ заметнее
(две разные цифры под одной строкой), так что откладывать нельзя.

### Правка 5: эпистемические теги на карточках результата

Использовать готовые классы из канона (`basis-design-system.css:94-97`, подключены
глобально — импорт не нужен) на заголовках карточек вместо мелкого текста внизу:
```jsx
// NumericTable — StressTestView.jsx:47
<Card header={<span className="tw-flex tw-items-center tw-gap-2">
  Эффект на финансовые показатели (за год, к базе последнего отчётного года)
  <span className="bs-tag-estimate">оценка</span>
</span>}>

// ExpertBlock — StressTestView.jsx:113
<Card header={<span className="tw-flex tw-items-center tw-gap-2">
  Разбор эксперта (ИИ на базе знаний платформы)
  <span className="bs-tag-judgment">суждение</span>
</span>}>

// «Как мы поняли ваш сценарий» — StressTestView.jsx:303
<Card header={<span className="tw-flex tw-items-center tw-gap-2">
  Как мы поняли ваш сценарий
  <span className="bs-tag-judgment">интерпретация ИИ</span>
</span>}>
```
Методологические сноски (`numeric.semantics` строка 81, `e.kb_note` строка 132)
оставить как есть — это ВТОРОЙ слой (подробности), теги — способ увидеть уровень
достоверности СРАЗУ, не читая мелкий текст внизу карточки.

### Правка 6: структурировать «Разбор эксперта»

`Side` (`StressTestView.jsx:89-111`) — добавить цветной левый бордер по знаку
(как советует конституция: «карточки с border-left акцентным — для факторов и
рисков») и визуально усилить сильные факторы:
```jsx
const Side = ({ title, sectors, companies, positive }) => (
  <div>
    <div className={`tw-text-[12px] tw-font-bold tw-uppercase tw-tracking-wide tw-mb-2 ${positive ? "tw-text-success" : "tw-text-danger"}`}>{title}</div>
    {sectors.map((s, i) => (
      <div key={`s${i}`}
        className="tw-mb-2 tw-pl-3 tw-border-l-2"
        style={{ borderColor: positive ? "var(--bs-up)" : "var(--bs-down)", opacity: s.strength === 1 ? 0.75 : 1 }}>
        <div className="tw-text-[13.5px] tw-font-semibold tw-text-text-primary">
          {s.sector}
          <span className={`bs-wind-tag ${positive ? "bs-wind-up" : "bs-wind-down"} tw-ml-2`}>{STRENGTH[s.strength] || ""}</span>
        </div>
        <div className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">{s.why}</div>
      </div>
    ))}
    {companies.length > 0 && (
      <div className="tw-mt-3 tw-flex tw-flex-col tw-gap-1.5">
        {companies.map((c, i) => (
          <div key={`c${i}`}
            className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug tw-pl-3 tw-border-l-2"
            style={{ borderColor: positive ? "var(--bs-up)" : "var(--bs-down)" }}>
            <span className="tw-font-mono tw-font-semibold tw-text-text-primary">{c.ticker}</span> — {c.why}
          </div>
        ))}
      </div>
    )}
    {!sectors.length && !companies.length && <div className="tw-text-[12.5px] tw-text-text-tertiary">—</div>}
  </div>
);
```
Плюс: если `sectors.length + companies.length > 6`, обрезать до 6 и добавить
«Показать все ▾» — тот же паттерн `showAll`, что уже есть в `NumericTable`/`QualTable`
(строки 44, 138) — сейчас `ExpertBlock` единственный из трёх блоков результата БЕЗ
прогрессивного раскрытия, хотя количество секторов/компаний непредсказуемо (зависит
от ответа ИИ) и потенциально не ограничено.

### Правка 7: заполнить пустое состояние готовыми сценариями (без LLM)

Новый третий блок ввода — грид из 6 пресетов, дергает уже существующий
`/api/stress-test/scenarios` + `/api/stress-test/impact`. Результат рендерится
существующим `QualTable` без изменений — формат ответа `/impact` совпадает 1:1.

```jsx
// добавить рядом с остальным состоянием, ~StressTestView.jsx:181
const [presets, setPresets] = useState([]);
const [presetResult, setPresetResult] = useState(null);
const [presetKey, setPresetKey] = useState(null); // какой пресет сейчас грузится

useEffect(() => {
  fetch(`${apiUrl}/api/stress-test/scenarios`)
    .then((r) => (r.ok ? r.json() : { scenarios: [] }))
    .then((d) => setPresets(d.scenarios || []))
    .catch(() => {});
}, [apiUrl]);

const runPreset = (key) => {
  setPresetKey(key); setPresetResult(null); setAskResult(null); setNumResult(null);
  fetch(`${apiUrl}/api/stress-test/impact?scenario=${key}`)
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((d) => { setPresetResult(d); setPresetKey(null); })
    .catch(() => setPresetKey(null));
};
```
```jsx
// новая карточка — вставить ПОСЛЕ «Или задайте уровни точно» (~StressTestView.jsx:286),
// это и есть контент для пустого пространства из находки 8
{presets.length > 0 && (
  <Card header="Готовые сценарии (детерминированный расчёт, без ИИ-интерпретации — быстрее и без риска неверно понять вопрос)">
    <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 lg:tw-grid-cols-3 tw-gap-3">
      {presets.map((p) => (
        <button key={p.key} type="button" onClick={() => runPreset(p.key)}
          disabled={presetKey === p.key}
          className="bs-ai-plan tw-text-left tw-bg-transparent tw-w-full tw-cursor-pointer disabled:tw-opacity-60">
          <div className="tw-text-[13.5px] tw-font-semibold tw-text-text-primary tw-mb-1">{p.label}</div>
          <div className="tw-text-[12px] tw-text-text-secondary tw-leading-snug">{p.description}</div>
        </button>
      ))}
    </div>
  </Card>
)}
...
{presetResult && !presetResult.error && (
  <>
    <Card header="Как мы поняли сценарий">
      <div className="tw-text-[14px] tw-text-text-primary">{presetResult.scenario?.description}</div>
    </Card>
    <QualTable qual={presetResult} />
  </>
)}
```
Это не только закрывает жалобу «бедновато» реальным содержимым, а не декором, но
и даёт пользователю БЫСТРЫЙ путь без ожидания LLM и без риска, что свободный текст
поймут неточно (сам баннер сверху предупреждает именно об этом риске у `/ask`).

### Правка 8: шрифты — точечный оверрайд на этот экран

Системная проблема (весь `design/primitives.jsx` держится на Inter Display/
JetBrains Mono) больше одного экрана — чинить весь `tailwind.config.js` не в
объёме этого ТЗ. Для ЭТОГО экрана — обёрточный класс, аналогично тому, как
`.cc-root` переопределяет токены для карточки компании (`tokens.css:307-369`):
```css
/* добавить в любой уже подключённый CSS-файл, например styles/stress-test.css (новый) */
.stress-test-view, .stress-test-view .tw-font-mono { font-family: var(--bs-mono) !important; }
.stress-test-view h2.tw-font-display { font-family: var(--bs-serif) !important; }
```
```jsx
// StressTestView.jsx:217 — было
<div className="tw-flex tw-flex-col tw-gap-5">
// стало
<div className="stress-test-view tw-flex tw-flex-col tw-gap-5">
```
Флагаю отдельно владельцу: если `design/primitives.jsx`/`tailwind.config.js`
переиспользуются на других незамигрированных экранах (не только здесь), точечный
фикс по одному экрану за раз — тактика затыкания дыр; в какой-то момент нужен
системный проход по `tailwind.config.js` (`fontFamily.mono`/`fontFamily.display`)
разом на все потребители — вне объёма этого документа, фиксирую как находку.

### Правка 9 (низкий приоритет): бакеты через `.bs-wind-tag`

`StressTestView.jsx:12-18`:
```jsx
// было
const BUCKETS = [
  { min: 8, label: "▲▲", cls: "tw-text-success", title: "сильно позитивно" },
  { min: 2, label: "▲", cls: "tw-text-success", title: "позитивно" },
  { min: -2, label: "─", cls: "tw-text-text-tertiary", title: "нейтрально / слабо" },
  { min: -8, label: "▼", cls: "tw-text-danger", title: "негативно" },
  { min: -Infinity, label: "▼▼", cls: "tw-text-danger", title: "сильно негативно" },
];
// стало
const BUCKETS = [
  { min: 8, label: "▲▲", cls: "bs-wind-up", title: "сильно позитивно" },
  { min: 2, label: "▲", cls: "bs-wind-up", title: "позитивно" },
  { min: -2, label: "─", cls: "bs-wind-neutral", title: "нейтрально / слабо" },
  { min: -8, label: "▼", cls: "bs-wind-down", title: "негативно" },
  { min: -Infinity, label: "▼▼", cls: "bs-wind-down", title: "сильно негативно" },
];
```
и в `QualTable` (строка 153) заменить `<span className={\`tw-font-semibold tw-flex-shrink-0 ${b.cls}\`}>`
на `<span className={\`bs-wind-tag ${b.cls}\`}>`.

## Готовый JSX/CSS для критичных правок

Самое весомое и самое дешёвое — Правка 2 (однострочный по сути фикс сортировки,
исправляет корневую причину «непонятно, кто пострадал больше всех») и Правка 3
(замена самодельного `DeltaCell` на готовый `Delta` — глиф ▲/▼ везде разом). Обе
готовы к переносу без адаптации, см. полный код выше в Правках 2 и 3.

Правка 1 (`ImpactSignal`) — самая заметная по эффекту для жалобы «бедновато» и
для прямого требования конституции про «вердикт поверх данных»; полный код — см.
Правку 1 целиком, компонент самодостаточен (использует уже импортированные `Card`
и переиспользуемый `ImpactBar`).

## Чего НЕ менять (важно!)

- Общая архитектура входа: «спроси текстом» + «задай точные уровни» — два разных
  режима под разные типы вопросов, это правильное продуктовое решение, не сводить
  в один интерфейс.
- Бакеты направления `▲▲/▲/─/▼/▼▼` (`BUCKETS`, `StressTestView.jsx:12-18`) как
  таксономия — честный отказ от псевдоточных процентов там, где движок реально не
  может их посчитать («Только направление... величину этих эффектов мы числом не
  оцениваем», строка 166) — держится на реальном ограничении движка, не убирать
  и не пытаться превратить в проценты.
- Прогрессивное раскрытие «Показать все N» на `NumericTable`/`QualTable` (пороги
  20 и 16 строк, строки 45, 141) — уже сделано ровно по чек-листу, только
  распространить на `ExpertBlock` (Правка 6), не переделывать существующее.
  Аналогично `BOND_GROUP_CAP`-паттерн честной деградации в других разделах сайта
  — прецедент, что уже одобрен.
- Текст демо-дисклеймера сверху (`StressTestView.jsx:220-226`) — по содержанию
  исчерпывающий и честный (перечисляет конкретные ограничения движка, не общие
  фразы), трогать формулировки не нужно, только не дублировать его тон ниже
  (Правка 5/13).
- Сортировка «голубые фишки первыми» как ВЕРХНЕУРОВНЕВАЯ группировка
  (`stress_numeric.py:178`, `not c["is_blue_chip"]`) — прямое продуктовое решение
  владельца (см. комментарий `StressTestView.jsx:9`), Правка 2 чинит только
  ранжирование ВНУТРИ группы, группировку не трогает.
- `coverage`/`factors_covered`/честная деградация «нет данных ≠ подтверждённый
  ноль» (`stress_scenarios.py:120-123`, `compute_impact`) — важная методологическая
  гарантия движка, за пределами этого ТЗ, но не подлежит упрощению.
- Медный акцент, `Card`/`Badge` (глубина, hover, бордеры) — визуальный язык самих
  карточек уже корректный, проблема в СОДЕРЖИМОМ карточек, не в их обрамлении.

## Оценка трудозатрат

- Правка 1 (`ImpactSignal`, сигнальный слой) — **M** (~3-4 часа: новый компонент +
  подключение в двух местах рендера + проверка на пустых/крайних сценариях).
- Правка 2 (фикс сортировки, бэкенд) — **S** (~30 минут, изолированное изменение
  одной функции + быстрый ручной прогон сценария «нефть $45»).
- Правка 3 (глиф ▲/▼ через `Delta`) — **S** (~45 минут, замена одного компонента).
- Правка 4 (дедуп обычка/префов) — **S/M** (~2 часа фронт; расхождение SNGS/SNGSP
  зафиксировать отдельным тикетом аналитику данных, не оценивается здесь).
- Правка 5 (эпистемические теги) — **S** (~1 час, точечные классы в 3 местах).
- Правка 6 (структура `ExpertBlock`) — **M** (~3 часа: бордеры + условное
  прогрессивное раскрытие).
- Правка 7 (готовые сценарии из `/scenarios`+`/impact`) — **M** (~4 часа: новый
  fetch + грид пресетов + переиспользование `QualTable` для результата —
  дешевле, чем кажется, именно благодаря совпадению формата данных).
- Правка 8 (шрифты, точечный скоуп) — **S** (~1 час на этот экран; системный
  проход по `tailwind.config.js` — отдельная задача, не оценивается здесь).
- Правка 9 (бакеты через `.bs-wind-tag`) — **S** (~30 минут).
- Правки 11-14 (бейдж «ГФ», переиспользование `Table`, тон дисклеймеров, Enter на
  числовых полях) — **S** суммарно (~1.5 часа все вместе).

**Итого по всему документу: L (день+)**, но Правки 2 и 3 — это буквально до часа
суммарно и закрывают самую большую по цене находку (у пользователя физически не
получалось увидеть, кто пострадал сильнее всех) — их стоит смёрджить первыми,
отдельно от остального. Правки 1 и 7 — следующий по значимости шаг (сигнальный
слой + заполнение пустого состояния реальной функциональностью), день на двоих.
