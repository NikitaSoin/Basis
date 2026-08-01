/**
 * Адреса разделов и вкладок платформы — ОДИН источник правды.
 *
 * Владелец, 2026-07-31: «по вкладкам в каждом из блоков (рынок/обозреватель/портфель)
 * не появились страницы под каждую вкладку». До этого адрес менялся только при выборе
 * компании и при переключении верхних разделов; вкладки ВНУТРИ разделов (Акции /
 * Облигации / Фьючерсы / Фонды в «Рынке», Состав / Риск / Корреляции / Индекс качества
 * в «Портфеле») своих адресов не имели — их нельзя было ни переслать, ни
 * проиндексировать, и заголовок вкладки браузера у них был общий.
 *
 * Почему отдельный модуль: функция нужна и в App.js, и внутри самих разделов
 * (MarketNeo, PortfolioViews, ObsPanels). Держать её в App.js и прокидывать пропами
 * через три уровня — лишний шум; здесь она в одном экземпляре, и формат адресов
 * правится в одном месте.
 */

// Заголовки вкладок: у каждой свой, иначе в браузере и в выдаче все вкладки раздела
// выглядят одинаково. Ключ — «раздел:вкладка».
import { trackPageView, logPageView, logAction } from "./analytics";

const TAB_TITLES = {
  // Рынок
  "companies:stocks": "Акции Мосбиржи: котировки и справедливая цена — Basis",
  "companies:bonds": "Облигации: доходность, риск, рейтинг — Basis",
  "companies:futures": "Фьючерсы Мосбиржи: плечо, ГО, экспирация — Basis",
  "companies:funds": "Фонды БПИФ и ETF: состав и комиссии — Basis",
  "companies:spot": "Валюта и металлы на Мосбирже — Basis",
  // Портфель
  "portfolio:composition": "Состав портфеля: доли, секторы, эмитенты — Basis",
  "portfolio:compare": "Сравнение портфеля с индексом — Basis",
  "portfolio:returns": "Доходность портфеля и оценка — Basis",
  "portfolio:risk": "Риск портфеля: волатильность, просадка, VaR — Basis",
  "portfolio:correlation": "Матрица корреляций портфеля — Basis",
  "portfolio:quality": "Индекс качества портфеля — Basis",
  "portfolio:ai-diagnosis": "ИИ-диагноз портфеля: уязвимости — Basis",
  "portfolio:stress": "Стресс-тестирование портфеля — Basis",
};

export function tabTitle(view, tab) {
  return TAB_TITLES[`${view}:${tab}`] || null;
}

/**
 * Меняет адрес и заголовок под выбранную вкладку раздела.
 * pushState, а не replaceState: переход между вкладками — шаг истории, чтобы «назад»
 * возвращал на предыдущую вкладку, а не выкидывал с платформы.
 */
export function syncTabUrl(view, tab) {
  try {
    if (!view || !tab) return;
    const url = `/?view=${encodeURIComponent(view)}&tab=${encodeURIComponent(tab)}`;
    if (window.location.pathname + window.location.search !== url) {
      window.history.pushState({ view, tab }, "", url);
      // Вкладки разделов меняют адрес в обход syncUrl — без этой строки переходы
      // «Акции → Облигации» или «Состав → Риск» в аналитике не видны вовсе.
      trackPageView(url);
      logPageView();
      logAction("вкладка раздела", { view, tab });
    }
    const t = tabTitle(view, tab);
    if (t) document.title = t;
  } catch {
    // адресная строка — не критичный путь: сломать навигацию из-за неё нельзя
  }
}
