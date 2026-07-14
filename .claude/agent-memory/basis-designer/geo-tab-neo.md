---
name: geo-tab-neo
description: GeoTab.jsx (вкладка «Геополитика», geo-system v0.9) — новый компонент для новой схемы geo.json; found + fixed a broken JSON in NVTK/geo.json
metadata:
  type: project
---

Вкладка «Геополитика» получила новый компонент `frontend/Basis/src/company/GeoTab.jsx` +
`frontend/Basis/src/styles/geo.css`, подключённый в `CompanyCardView.jsx` через новую
функцию-роутер `renderGeoTab()` (вызывается вместо `renderGeo()` в JSX на месте
`tab === "geo"`): если `geoJson.gre_profile` — массив с элементами (новая схема
geo-system v0.9, пилот LKOH/ROSN/NVTK/GAZP, 2026-07-12), рендерит `<GeoTab/>`; иначе
падает обратно на старый `renderGeo()` (старая схема meta/exposure_profile/factors/
bottom_line + markdown-фолбэк) — так остальные ~258 компаний, ещё не мигрированные на
новую методику, не ломаются. `onNavigateTab={setTab}` прокинут в GeoTab (в отличие от
InstitutionsTab, где prop есть, но не прокинут — см. [[institutions-tab-neo]]) — GeoTab
использует его для перехода на вкладку «Институты» из карточек `inst_overlap` в
disagreements.

**Находка данных (не дизайна): `backend/companies/NVTK/geo.json` был БИТЫМ JSON** —
пропущенная закрывающая `}` у объекта `{"type":"barometer_note", "text":"..."}` в массиве
`disagreements` (строка 116). Файл читался как текст (Read tool это не ловит), но
`JSON.parse`/`json.load` падали. Исправлено точечно (добавлена `}`), проверено
`json.load` на всех 4 файлах после фикса — ОК. **Если в будущем встретится вкладка,
которая на конкретном тикере рендерится пусто/как markdown-фолбэк при formally
существующем geo.json/institutions.json — ПЕРВЫМ делом проверь `python3 -c "import
json; json.load(open(...))"`, не только структуру полей.**

**Схема РАСХОДИТСЯ с идеализированным описанием задачи в двух местах, подтверждено
на всех 4 реальных файлах:**
1. `gre_profile[i]` в реальности имеет поля `{key, label, score, type, rationale,
   trigger}` — НЕ `{score, anchor, drivers[], triggers_up, triggers_down}`, как было
   в постановке. Рендер сделан по реальным полям.
2. `macro_handoff_cited` НЕ имеет единообразной структуры между компаниями: у ROSN —
   структурированные `G_scores_verbatim`/`scenarios_verbatim` (объекты по ключам G1..G13
   /S1..S4), у LKOH/GAZP/NVTK — то же самое текстом внутри `scenario_lean`/
   `verbatim_note` (строка вида `"S1_breakthrough 5% 6м / 10% 18м; ..."`). Компонент
   поддерживает оба варианта: `scenarioProbText()` сначала смотрит `scenarios_verbatim[key]`,
   при отсутствии — regex по конкатенации всех строковых листьев объекта
   (`flattenStrings()`). Поле `regions` (svo/middle_east/atr) из идеализированной схемы
   ОТСУТСТВУЕT во всех 4 живых файлах — компонент его нигде не рендерит (не было на чём
   проверить формат; если появится, читать как оптional-блок, не полагаться на память).

**Полярность баллов ОБРАТНАЯ InstitutionsTab:** в gre_profile (E1-E15) БОЛЬШЕ = БОЛЬШЕ
гео-экспозиции/риска (напр. E12 «Госспрос и военная экономика» = 5.0 у Газпрома — это
плохо, максимальный риск донора), поэтому `scoreColor()` в GeoTab красит высокий балл
красным/`--neg`, низкий — зелёным/`--pos` — ЗЕРКАЛЬНО тому, что в InstitutionsTab.
Кластеризация E1-E15 — по смыслу `label` (`classifyGeo()`, 5 пакетов: SANC/TECH/OWN/
WAR/MACRO), тот же принцип «ключи не канонические между компаниями», что и у S1-S15 —
см. [[institutions-tab-neo]]. Порядок regex-правил важен: «контрсанкционный» содержит
подстроку «санкционный» — правило OWN (`контрсанкцион`) проверяется ПЕРЕД общим SANC
(`санкционн`), иначе E11 неверно попадает в санкционный кластер вместо
владельческого.

**Три канала трансляции в оценку (A_wacc/B_fcf/C_multiple)** — в отличие от Institutions
(одно число на канал), у гео `valuation_translation` — МАССИВ из нескольких пунктов на
канал (`{effect, channel, magnitude, rationale}`), плюс встречается `channel: "inst_owned"`
— пункты, которые explicitly НЕ гео (принадлежат вкладке «Институты», просто
задокументированы для анти-двойного-счёта) — они исключены из карточек A/B/C и показаны
отдельной строкой в collapsible «Как считали».

`causal_attribution.channels` — значения бывают со знаком `~` перед числом (ROSN:
`"~23%"`) — `parseFloat("~23%")` даёт `NaN`; сумма % не всегда 100 (NVTK добавляет
пятый ключ `residual`, вне фиксированного списка из 5 — компонент считает total только
по известным 5 ключам `ATTR5_DEFS`, `residual` не рендерится и не участвует в сумме).

Валидация: временный jest-smoke-тест (react-dom/client createRoot + act, читал реальные
`backend/companies/{LKOH,ROSN,NVTK,GAZP}/geo.json`) прогнан и удалён — все 4 рендерятся
без исключений, при отсутствии этого файла в репо не удивляться, он был одноразовым.

См. также [[institutions-tab-neo]] (тот же паттерн: hero + 3 канала + кластеризация по
label + markdown-фолбэк), [[bond-risk-render]] (canonical-парсинг + легаси-фолбэк).
