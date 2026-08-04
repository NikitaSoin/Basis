// =============================================================
// ЖИВОЙ ТУР ПО ПЛАТФОРМЕ — плоский конфиг шагов (Часть A плана
// «Живой тур по платформе + короткий лендинг с каруселью»,
// .claude/plans/expressive-bubbling-firefly.md).
//
// Каждый шаг — реальная навигация на реальный экран (никаких
// картинок/каруселей): `action`/`actionArg` говорят движку
// (tour/useTourEngine.js), что вызвать (`navigate(tab)` или
// `onOpenCompany(ticker)` из App.js), `selector` — что подсветить
// после того, как экран домонтируется (tour/tourLocator.js ждёт
// элемент, а не верит, что он уже есть).
//
// `data-tour="<id>"` — атрибут, который должен ДОСЛОВНО совпадать
// с `selector` ниже, расставлен точечно в JSX целевых компонентов:
//   market     → src/market/MarketNeo.jsx      (.mk-stack, грид карточек)
//   company    → src/company/CompanyCardView.jsx (карточка «Справедливая
//                цена по методике Basis» — на ДВУХ взаимоисключающих
//                ветках рендера: посчиталась/не посчиталась, поэтому
//                атрибут стоит на обеих — в DOM в любой момент только
//                одна из них)
//   screener   → src/screener/ScreenerCompareShell.jsx (.scmp-panel)
//   observer   → src/App.js (ObserverV2, секция «news» — дефолтная
//                при входе без forceSection)
//   portfolio  → src/portfolio/PortfolioViews.jsx (гостевой баннер
//                pf-guest-note ИЛИ пилюля «+ Добавить позицию» —
//                тоже взаимоисключающие ветки одного и того же экрана)
//   stress     → src/portfolio/StressTestView.jsx (.st-rail — пресеты
//                сценариев + слайдеры)
//
// Финальный шаг (stress, isLastStep) несёт доп. поле `outro` —
// короткая фраза про Ассистента, НЕ отдельный шаг тура (владелец:
// «краткий экскурс», Ассистент отдельным пунктом раздувал бы тур).
// =============================================================

const TOUR_STEPS = [
  {
    id: "market",
    action: "navigate",
    actionArg: "companies",
    selector: '[data-tour="market"]',
    placement: "bottom",
    title: "Рынок",
    body: "Все классы активов на одной карте — акции, облигации, фьючерсы, фонды, валюта и металлы. У каждой бумаги — потенциал к справедливой цене Basis, а не сигнал «купить/продать».",
  },
  {
    id: "company",
    action: "openCompany",
    actionArg: "ROSN",
    selector: '[data-tour="company"]',
    placement: "bottom",
    title: "Карточка компании",
    body: "Открыли разбор конкретной бумаги. Здесь — справедливая цена по методике Basis: само число, потенциал и честная пометка «модель», а не факт, плюс на чём оно основано.",
  },
  {
    id: "screener",
    action: "navigate",
    actionArg: "screener",
    selector: '[data-tour="screener"]',
    placement: "bottom",
    title: "Скринер",
    body: "Отфильтруйте весь рынок по метрикам Basis — справедливая цена, дивдоходность, риск — и получите список, а не догадки.",
  },
  {
    id: "observer",
    action: "navigate",
    actionArg: "overview",
    selector: '[data-tour="observer"]',
    placement: "bottom",
    title: "Обозреватель",
    body: "Рыночный фон одним взглядом: лента новостей, экономическая статистика, календарь отчётов, геополитика — то, что происходит вокруг ваших решений.",
  },
  {
    id: "portfolio",
    action: "navigate",
    actionArg: "portfolio",
    selector: '[data-tour="portfolio"]',
    placement: "bottom",
    title: "Портфель",
    body: "Соберите свои позиции — платформа посчитает состав, риск и качество. Без регистрации портфель сохраняется в этом браузере; чтобы не потерять его при смене устройства — зарегистрируйтесь.",
  },
  {
    id: "stress",
    action: "navigate",
    actionArg: "stress",
    selector: '[data-tour="stress"]',
    placement: "right",
    title: "Стресс-тестирование",
    body: "Что будет с рынком, если сдвинуть ставку, курс или нефть? Сценарный движок Basis показывает, кто пострадает, а кто выиграет — демо-версия на линейных коэффициентах, не прогноз.",
    outro: "Ассистент — в шапке сайта, один вопрос бесплатно без регистрации.",
  },
];

export default TOUR_STEPS;
