#!/usr/bin/env node
/**
 * Сплошная проверка: КУДА ВЕДУТ наши SEO-страницы и что с ними делает приложение.
 *
 * ЗАЧЕМ (владелец 2026-08-26): «вбил высокодоходные облигации — открылась SEO-страница, а
 * кнопка внизу вела на лендинг… и важно ВСЕ страницы проверить, что ссылки ведут на нужные
 * блоки, вкладки, с включёнными фильтрами». Поводом были две поломки, и обе тихие:
 *   1) все 8 кнопок на страницах инструментов стояли href="/" при подписи «раздел Рынок →
 *      Фонды» — 3262 страницы вели на главную;
 *   2) кнопка подборки вела на общий раздел без самой подборки, поэтому фильтр не включался.
 * Ни то, ни другое не ломало сборку и не давало ошибки в консоли — увидеть можно было только
 * глазами на живом сайте. Поэтому проверка нужна отдельная и повторяемая.
 *
 * 🔴 ПРОВЕРЯЕМ БОЕВОЙ САЙТ, А НЕ ЛОКАЛЬНУЮ build/. Локальная папка ничего не доказывает:
 * Timeweb собирает фронт у себя, и расхождение между тем, что собралось здесь, и тем, что
 * лежит на бою, — обычное дело (так уже ловили несоответствие бандлов).
 *
 * Что именно проверяется по каждому типу страницы:
 *   • страница отвечает 200 и в ней есть #seo-static (значит статика на месте);
 *   • у неё есть кнопка в приложение и она НЕ ведёт на «/» (главную);
 *   • адрес кнопки указывает на раздел, который приложение умеет открыть;
 *   • для подборок — кнопка несёт саму подборку (?preset=…), иначе фильтр не включится.
 *
 * Запуск:  node scripts/audit-seo-links.js  [https://inbasis.ru]
 * Выход:   код 1, если есть провалы — годится для проверки перед выкаткой.
 */

const SITE = (process.argv[2] || "https://inbasis.ru").replace(/\/$/, "");

// Разделы, которые приложение реально умеет открыть по адресу. Список сверен с App.js:
// VIEW_TABS (?view=…), VALID_TABS в MarketNeo (?tab=… внутри «Рынка») и OBS_SECTIONS.
const VIEWS = ["companies", "overview", "portfolio", "stress", "screener", "ai", "pricing"];
const MARKET_TABS = ["stocks", "bonds", "futures", "funds", "spot"];
const OBS = ["news", "economy", "pulse", "maps", "calendar", "reports", "corp-news",
             "macro", "geo", "institutions", "ai"];

// Что проверяем. `needPreset` — страница подборки: её кнопка обязана нести подборку,
// иначе человек попадёт в общий список без фильтра (жалоба владельца).
const PAGES = [
  { url: "/company/SBER/",                     what: "карточка компании" },
  { url: "/company/SBER/dividends/",           what: "карточка: дивиденды" },
  { url: "/company/SBER/finance/",             what: "карточка: финансы" },
  { url: "/company/SBER/spravedlivaya-tsena/", what: "карточка: справедливая цена" },
  { url: "/company/SBER/grafik/",              what: "карточка: график" },
  { url: "/company/SBER/prognoz/",             what: "карточка: прогноз" },
  { url: "/company/",                          what: "каталог компаний" },
  { url: "/bonds/RU000A10B487/",               what: "выпуск облигации" },
  { url: "/bonds/vdo/",                        what: "подборка ВДО",        needPreset: "vdo" },
  { url: "/bonds/ofz/",                        what: "подборка ОФЗ",        needPreset: "ofz" },
  { url: "/bonds/flotery/",                    what: "подборка флоатеров",  needPreset: "flotery" },
  { url: "/bonds/korotkie/",                   what: "подборка коротких",   needPreset: "korotkie" },
  { url: "/futures/SiU6/",                     what: "фьючерс" },
  { url: "/funds/AMFL/",                       what: "фонд" },
  { url: "/statistika/klyuchevaya-stavka/",    what: "макропоказатель" },
  { url: "/pokazateli/p-e/",                   what: "термин словаря", ctaOptional: true },
  { url: "/indeks/imoex/",                     what: "индекс" },
  { url: "/analiz-portfelya/",                 what: "лендинг: портфель" },
  { url: "/skrining-aktsiy/",                  what: "лендинг: скрининг" },
  { url: "/makroobzor-rossiyskoy-ekonomiki/",  what: "лендинг: макрообзор" },
  { url: "/geopolitika-i-rossiyskiy-rynok/",   what: "лендинг: геополитика" },
  { url: "/ii-pomoshchnik-investoru/",         what: "лендинг: ассистент" },
  { url: "/razbor-otchetnosti-kompaniy/",      what: "лендинг: разборы отчётности" },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 🔴 Сетевой сбой НЕ должен ронять проверку: канал до сайта рвётся произвольно (ловили
 *  дважды на API Вебмастера — «Tunnel connection failed»), и упавший на середине аудит
 *  выглядит как «проверка не прошла», хотя проверять он даже не начал. Три попытки, и
 *  только потом честный отчёт о недоступности. Пауза между страницами — чтобы не долбить. */
async function get(path, tries = 3) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(`${SITE}${path}?v=${Math.random().toString(36).slice(2)}`,
                            { redirect: "follow" });
      return { code: r.status, html: r.ok ? await r.text() : "" };
    } catch (e) {
      if (i === tries - 1) return { code: 0, html: "", err: String(e.cause || e).slice(0, 60) };
      await sleep(1500 * (i + 1));
    }
  }
}

/** Разобрать адрес кнопки и сказать, откроет ли приложение по нему что-то осмысленное. */
function judgeHref(href) {
  if (!href) return { ok: false, why: "кнопки в приложение нет вовсе" };
  if (href === "/" ) return { ok: false, why: "ведёт на ГЛАВНУЮ вместо своего раздела" };
  // Внутренняя ссылка на другую SEO-страницу — это нормально (перелинковка).
  if (!href.startsWith("/?")) return { ok: true, why: `ведёт на ${href}` };
  const q = new URLSearchParams(href.slice(2).replace(/&amp;/g, "&"));
  const view = (q.get("view") || "").toLowerCase();
  if (!VIEWS.includes(view)) return { ok: false, why: `?view=${view || "—"} — приложение такого раздела не знает` };
  const tab = (q.get("tab") || "").toLowerCase();
  if (view === "companies" && tab && !MARKET_TABS.includes(tab))
    return { ok: false, why: `?tab=${tab} — в «Рынке» такой вкладки нет` };
  const obs = (q.get("obs") || "").toLowerCase();
  if (view === "overview" && obs && !OBS.includes(obs))
    return { ok: false, why: `?obs=${obs} — в Обозревателе такого раздела нет` };
  return { ok: true, why: `открывает ${view}${tab ? " → " + tab : ""}${obs ? " → " + obs : ""}` };
}

(async () => {
  let bad = 0;
  console.log(`Проверяю ${PAGES.length} типов страниц на ${SITE}\n`);
  for (const p of PAGES) {
    const { code, html, err } = await get(p.url);
    await sleep(250);
    const problems = [];
    if (code !== 200) problems.push(err ? `сеть: ${err}` : `код ответа ${code}`);
    else {
      if (!html.includes('id="seo-static"')) problems.push("нет статического блока #seo-static");
      const m = html.match(/<a class="cta"[^>]*?href="([^"]*)"/);
      const href = m ? m[1].replace(/&amp;/g, "&") : null;
      const verdict = judgeHref(href);
      if (!verdict.ok && !(p.ctaOptional && !href)) problems.push(verdict.why);
      if (p.needPreset && href && !href.includes(`preset=${p.needPreset}`))
        problems.push(`кнопка не несёт подборку (?preset=${p.needPreset}) — фильтр не включится`);
      if (!problems.length) console.log(`  ✓ ${p.what.padEnd(30)} ${verdict.why}`);
    }
    if (problems.length) {
      bad++;
      console.log(`  ✕ ${p.what.padEnd(30)} ${p.url}`);
      problems.forEach((x) => console.log(`      → ${x}`));
    }
  }
  console.log(`\nИтог: ${PAGES.length - bad} в порядке, ${bad} с проблемами.`);
  process.exit(bad ? 1 : 0);
})();
