/**
 * Счётчик Яндекс.Метрики — ОДИН источник правды на весь проект.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫМ МОДУЛЕМ: у платформы ТРИ разных типа HTML, и они собираются разными
 * генераторами:
 *   1. SPA-оболочка            public/index.html                     — грузит приложение
 *   2. SEO-страницы (4692)     generate-seo-pages.js / -indicators.js — грузят приложение
 *   3. Страницы инструментов   generate-seo-instruments.js (3757)     — приложение НЕ грузят
 *
 * Третий тип — облигации, фонды и фьючерсы — чистый статический HTML без бандла. Если
 * ставить счётчик только внутри приложения, эти 3757 страниц выпадут из аналитики
 * полностью: именно на них приходит поисковый трафик по конкретным выпускам, и мы бы
 * не увидели ни одного такого визита.
 *
 * ПОЧЕМУ СНИППЕТ, А НЕ ИНИЦИАЛИЗАЦИЯ ИЗ КОДА ПРИЛОЖЕНИЯ: Метрика просит размещать
 * счётчик как можно ближе к началу страницы, чтобы визит засчитался даже если человек
 * закроет вкладку через секунду. Инициализация после монтирования React этого не даёт.
 * Поэтому загрузка — сниппетом в <head>, а приложение только досылает просмотры при
 * переходах (см. src/analytics.js).
 *
 * 🔴 НОМЕР МЕНЯТЬ ТОЛЬКО ЗДЕСЬ. Он же кладётся в window.__BASIS_METRIKA_ID__, откуда его
 * читает приложение — так номер не приходится дублировать ещё и в .env.
 */
"use strict";

const METRIKA_ID = "111213378";

/**
 * HTML счётчика для вставки в <head>. Пустая строка, если номер не задан —
 * тогда наружу не уходит ничего.
 */
function metrikaSnippet() {
  if (!METRIKA_ID) return "";
  return `<script>window.__BASIS_METRIKA_ID__=${JSON.stringify(METRIKA_ID)};
(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}
k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
(window,document,"script","https://mc.yandex.ru/metrika/tag.js?id=${METRIKA_ID}","ym");
ym(${METRIKA_ID},"init",{ssr:true,webvisor:true,clickmap:true,accurateTrackBounce:true,trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/${METRIKA_ID}" style="position:absolute;left:-9999px" alt=""></div></noscript>`;
}

module.exports = { METRIKA_ID, metrikaSnippet };
