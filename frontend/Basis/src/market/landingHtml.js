// Лендинг v5 — КОРОТКИЙ. Владелец (2026-08-04): «лендинг очень перегружен, его нужно
// сильно короче и в двух словах раскрыть ценность и показать картинки с платформы».
// Было 14 секций / 435 строк — стало четыре HTML-секции плюс карусель реальных
// скриншотов между ними (React-компонент market/LandingCarousel.jsx, вставляется
// в LandingNeo.jsx между LANDING_TOP и LANDING_BOTTOM).
//
// 🔴 ПОЧЕМУ ФАЙЛ РАЗБИТ НА ДВА ЭКСПОРТА, а не остался одной строкой: карусель —
// единственный интерактивный узел страницы, ей нужен настоящий React (scroll-snap +
// IntersectionObserver + автоплей), а вокруг неё — статичная разметка. Разрез идёт
// ровно по месту вставки: LANDING_TOP заканчивается Trust Band, LANDING_BOTTOM
// начинается с блока эпистемических статусов.
//
// Что вырезано и почему (решение по плану expressive-bubbling-firefly.md):
//   • WHY — тезис уже сказан в hero, второй раз теми же словами;
//   • 01 MARKET, 03 OBSERVER, 04 SCREENER, 05 PORTFOLIO, 06 STRESS, 07 ASSISTANT —
//     каждая была «проза + мокап раздела»; мокапы заменены СКРИНШОТАМИ САМИХ
//     разделов в карусели, проза сжата до одной подписи под кадром;
//   • 01b BONDS — факт про 3100 выпусков остаётся в Trust Band, отдельная секция
//     раздувала бы карусель шестым кадром;
//   • 02 FAIR VALUE METHOD — семиуровневая раскладка баров была декоративным
//     мокапом: такого экрана в продукте нет, а методику мы намеренно не
//     раскрываем целиком (решение владельца);
//   • HOW IT WORKS («4 слоя чтения») — педагогика, ей место в туре по платформе
//     (tour/tourSteps.js), а не на коротком лендинге;
//   • pillars внутри блока доверия — дублировали то, что теперь видно на кадрах.
//
// Правила тона (сохранены от v4, нарушать = вернуться к рекламной редакции):
// утверждение о ПРЕДМЕТЕ, а не о читателе; деталь вместо эпитета (264 / 3100 / 7 —
// фактура); полные предложения без парцелляции; ЗАПРЕЩЕНЫ «на самом деле», «правда»,
// «секрет», «сбой»; ограничения формулируются как принцип («не брокер: сделок не
// исполняем»), а не как оправдание.
//
// Разметка в словаре styles/landing.css (band/trust/rv/sec-head…), CTA → data-route
// (роутинг в LandingNeo). Карточка в hero и бегущая строка — ЖИВЫЕ (LandingNeo
// подтягивает котировки и метрики каждые 8с), это не мокап.

// ---- ВЕРХ: hero + полоса фактов -------------------------------------------------
export const LANDING_TOP = `

<span id="top"></span>
<!-- HERO -->
<section class="hero">
  <div class="hero-bg"><canvas id="heat"></canvas><div class="mesh"></div><div class="mesh v"></div></div>
  <div class="wrap">
    <div>
      <div class="hero-badge rv"><i></i> Независимая аналитика российского рынка · второе мнение перед решением</div>
      <h1 class="rv d1">Платформа поддержки<br><span class="grad">инвестиционных решений</span></h1>
      <p class="hero-sub rv d2">Базис разбирает весь российский рынок по единой методике: 264 компании и 3100 выпусков облигаций — от финансовой отчётности до макроэкономики, геополитики и корпоративного управления. Платформа показывает справедливую стоимость бумаги и риски, которые не видны в котировках; решение остаётся за вами. Мы не брокер: сделок не исполняем и торговых сигналов не даём.</p>
      <div class="hero-actions rv d3">
        <a class="btn btn-primary btn-lg" href="#" data-route="companies">Открыть платформу →</a>
        <a class="btn btn-ghost btn-lg" href="#" data-route="rosn">Пример — Роснефть</a>
      </div>
    </div>

    <div class="cock rv d2">
      <div class="cock-card">
        <div class="cc-h">
          <div class="cc-logo">Р</div>
          <div class="cc-hid"><b>Роснефть</b><span>ROSN · Нефтегаз</span></div>
          <div class="cc-hpx"><b>564,20 ₽</b><span>▲ 0,84 %</span></div>
        </div>
        <div class="cc-b">
          <div class="cc-fv"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
          <div class="cc-mx">
            <div class="cc-m"><div class="l">P / E</div><div class="v">5,0×</div><div class="bar"><i style="width:78%;background:var(--pos)"></i></div></div>
            <div class="cc-m"><div class="l">ND/EBITDA</div><div class="v">1,3×</div><div class="bar"><i style="width:55%;background:var(--amber)"></i></div></div>
            <div class="cc-m"><div class="l">Дивиденд</div><div class="v">10,4%</div><div class="bar"><i style="width:68%;background:var(--accent)"></i></div></div>
          </div>
          <div class="cc-tags"><span class="tag tag-f">факт</span><span class="tag tag-e">оценка</span><span class="tag tag-j">суждение</span></div>
          <div class="cc-live"><span class="cc-live-dot"></span>оценка пересчитывается на каждый запрос — от текущей котировки и кривой ОФЗ</div>
        </div>
      </div>
      <div class="cock-float cf1"><div class="ic" style="background:var(--violet-soft)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" stroke-width="1.8" stroke-linecap="round"><path d="M3 17l5-6 4 3 5-7 4 5"/></svg></div><div><div class="ft">Сценарий · эскалация</div><div class="fv" style="color:var(--violet)">ROS −5%</div></div></div>
      <div class="cock-float cf2"><div class="ic" style="background:color-mix(in srgb,var(--amber) 14%,transparent)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/></svg></div><div><div class="ft">Главный риск</div><div class="fv" style="color:var(--amber)">Крепкий рубль</div></div></div>
    </div>
  </div>

  <div class="ticker" id="ticker"><div class="ticker-row" id="tickerRow"></div></div>
</section>

<!-- TRUST BAND — 4 факта вместо шести: метрики портфеля и сценарии стресс-теста
     теперь показаны на самих кадрах карусели, повторять их цифрой незачем. -->
<section class="trust">
  <div class="wrap">
    <div class="trust-grid">
      <div class="stat rv"><div class="num" data-count="264">0</div><div class="lbl">компаний, разобранных по единой методике</div></div>
      <div class="stat rv d1"><div class="num" data-count="3000" data-suffix="+">0</div><div class="lbl">выпусков облигаций: доходность против&nbsp;риска</div></div>
      <div class="stat rv d2"><div class="num" data-count="7">0</div><div class="lbl">связанных разделов анализа по компании</div></div>
      <div class="stat rv d3"><div class="num mono">0–100</div><div class="lbl">композитный балл в скринере</div></div>
    </div>
  </div>
</section>

`;

// ---- НИЗ: статусы утверждений + финальный CTA + подвал --------------------------
export const LANDING_BOTTOM = `

<!-- DIFFERENTIATOR -->
<section class="band band-alt" id="trust-sec">
  <div class="wrap">
    <div class="sec-head diff-head">
      <div class="eyebrow rv">Основание доверия</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">У каждого утверждения указан его статус</h2>
      <p class="lead rv d2">Прозрачность здесь — формат изложения, а не декларация: видно, что именно перед вами — установленный факт, модельный расчёт, аналитическое суждение или условный сценарий. И видно, где платформа ответа не даёт.</p>
    </div>
    <div class="fej">
      <div class="fc rv" style="--c:var(--ink-3)"><div class="tg">Факт</div><h4>Подтверждён источником</h4><p>Отчётность, котировки, официальные данные — с датой и ссылкой.</p></div>
      <div class="fc rv d1" style="--c:var(--heat-d)"><div class="tg">Оценка</div><h4>Модельный расчёт</h4><p>Получено из модели с явными допущениями, которые можно проверить.</p></div>
      <div class="fc rv d2" style="--c:var(--accent)"><div class="tg">Суждение</div><h4>Интерпретация</h4><p>Аналитическое мнение, а не предсказание — с честными оговорками.</p></div>
      <div class="fc rv d3" style="--c:var(--violet)"><div class="tg">Сценарий</div><h4>Условный путь</h4><p>«Если X — тогда Y»: что должно произойти и что опровергнет вывод.</p></div>
    </div>
  </div>
</section>

<!-- FINAL CTA -->
<section class="final">
  <div class="wrap">
    <div class="eyebrow rv">Начать</div>
    <h2 class="rv d1">Решение остаётся за вами.<br>Аналитическая работа — за нами</h2>
    <p class="lead rv d2" style="margin:16px auto 0;text-align:center">Откройте разбор конкретной компании или платформу целиком.</p>
    <div class="hero-actions rv d2">
      <a class="btn btn-primary btn-lg" href="#" data-route="companies">Открыть платформу →</a>
      <a class="btn btn-ghost btn-lg" href="#" data-route="rosn">Пример — Роснефть</a>
    </div>
    <div class="final-reg rv d3">
      <p class="final-reg-p">Для дальнейшего комфортного использования платформы рекомендуем пройти регистрацию — это быстро и не займёт много времени.</p>
      <a class="feat-link" href="#" data-route="login">Зарегистрироваться <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
    </div>
  </div>
</section>

<footer>
  <div class="wrap">
    <a class="brand" href="#top"><span class="bm">B</span>Базис</a>
    <p class="fnote">© 2026 Платформа Базис · Не является индивидуальной инвестиционной рекомендацией. Независимый аналитический сервис — не брокер, сделок не исполняет.</p>
    <div class="flinks"><a href="#platform">Экраны платформы</a><a href="#trust-sec">Статусы утверждений</a><a href="#" data-route="companies">Платформа</a></div>
  </div>
</footer>

`;

// Совместимость: старый default-импорт продолжает отдавать страницу целиком —
// без карусели (она вставляется только там, где есть React, см. LandingNeo.jsx).
const LANDING_HTML = LANDING_TOP + LANDING_BOTTOM;
export default LANDING_HTML;
