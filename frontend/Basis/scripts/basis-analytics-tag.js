/**
 * Подключение собственного сборщика аналитики — ОДНО место на весь проект.
 *
 * Парный модуль к metrika.js и по той же причине: каркасов HTML три, генераторы разные,
 * и стоит забыть один из них — из аналитики выпадает целый класс страниц. Именно так и
 * было: сбор жил внутри приложения, а 3757 страниц инструментов приложение не грузят.
 *
 * Сам сборщик — public/basis-analytics.js, отдельным файлом, а не встроенным кодом:
 * он один на все страницы, браузер закэширует его один раз, и правка не требует
 * пересборки всех восьми тысяч страниц.
 */
"use strict";

// Тот же порядок источников, что у generate-seo-pages.js: переменная сборки, затем
// боевой адрес по умолчанию — чтобы статические страницы работали и без окружения.
const API_BASE = process.env.REACT_APP_API_URL || process.env.BASIS_API
  || "https://nikitasoin-basis-a772.twc1.net";

function analyticsSnippet() {
  return `<script>window.__BASIS_API_URL__=${JSON.stringify(API_BASE)};</script>
<script src="/basis-analytics.js" defer></script>`;
}

module.exports = { API_BASE, analyticsSnippet };
