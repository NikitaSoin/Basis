// Авто-извлечено из docs/Lending_new.zip (Landing v3.html). Разметка лендинга;
// CTA → data-route (роутинг в LandingNeo). Стили — styles/landing.css.
const LANDING_HTML = `

<span id="top"></span>
<!-- HERO -->
<section class="hero">
  <div class="hero-bg"><canvas id="heat"></canvas><div class="mesh"></div><div class="mesh v"></div></div>
  <div class="wrap">
    <div>
      <div class="hero-badge rv"><i></i> Независимая аналитика российского рынка · второе мнение перед решением</div>
      <h1 class="rv d1">Системный анализ<br><span class="grad">российского рынка</span></h1>
      <p class="hero-sub rv d2">Вы анализируете сами, но полный разбор — это много работы: фундамент компании, сектор, макро, геополитика, рыночный контекст, риск портфеля — и всё это меняется на волатильном рынке. Базис делает это системно: шесть связанных уровней анализа по каждой компании сходятся в справедливую цену с прозрачной методикой. Плюс обзор рынка, облигации, скринер и портфельная аналитика.</p>
      <div class="hero-actions rv d3">
        <a class="btn btn-primary btn-lg" href="#" data-route="companies">Открыть платформу →</a>
        <a class="btn btn-ghost btn-lg" href="#" data-route="rosn">Пример — Роснефть</a>
      </div>
      <div class="qlinks rv d4">
        <a href="#" data-route="companies"><span class="qd" style="background:var(--accent)"></span>Рынок</a>
        <a href="#" data-route="screener"><span class="qd" style="background:var(--violet)"></span>Скринер</a>
        <a href="#observer"><span class="qd" style="background:var(--pos)"></span>Обозреватель</a>
        <a href="#portfolio"><span class="qd" style="background:var(--amber)"></span>Портфельная аналитика</a>
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
          <div class="cc-tone"><span style="width:9px;height:9px;border-radius:50%;background:var(--accent);flex-shrink:0"></span><div><div class="l">Что важно сейчас</div><div class="v">Дешёвый кэшфлоу, но дивиденд чувствителен к рублю</div></div></div>
          <div class="cc-fv"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
          <div class="cc-mx">
            <div class="cc-m"><div class="l">P / E</div><div class="v">5,0×</div><div class="bar"><i style="width:78%;background:var(--pos)"></i></div></div>
            <div class="cc-m"><div class="l">ND/EBITDA</div><div class="v">1,3×</div><div class="bar"><i style="width:55%;background:var(--amber)"></i></div></div>
            <div class="cc-m"><div class="l">Дивиденд</div><div class="v">10,4%</div><div class="bar"><i style="width:68%;background:var(--accent)"></i></div></div>
          </div>
          <div class="cc-tags"><span class="tag tag-f">факт</span><span class="tag tag-e">оценка</span><span class="tag tag-j">суждение</span></div>
        </div>
      </div>
      <div class="cock-float cf1"><div class="ic" style="background:var(--violet-soft)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" stroke-width="1.8" stroke-linecap="round"><path d="M3 17l5-6 4 3 5-7 4 5"/></svg></div><div><div class="ft">Сценарий · эскалация</div><div class="fv" style="color:var(--violet)">ROS −5%</div></div></div>
      <div class="cock-float cf2"><div class="ic" style="background:color-mix(in srgb,var(--amber) 14%,transparent)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/></svg></div><div><div class="ft">Главный риск</div><div class="fv" style="color:var(--amber)">Крепкий рубль</div></div></div>
    </div>
  </div>

  <div class="ticker" id="ticker"><div class="ticker-row" id="tickerRow"></div></div>
</section>

<!-- TRUST BAND -->
<section class="trust">
  <div class="wrap">
    <div class="trust-grid">
      <div class="stat rv"><div class="num" data-count="262">0</div><div class="lbl">компаний под анализом</div></div>
      <div class="stat rv d1"><div class="num" data-count="3000" data-suffix="+">0</div><div class="lbl">облигаций: доходность vs&nbsp;риск</div></div>
      <div class="stat rv d2"><div class="num" data-count="7">0</div><div class="lbl">разделов в карточке компании</div></div>
      <div class="stat rv d3"><div class="num mono">0–100</div><div class="lbl">композитный балл в скринере</div></div>
      <div class="stat rv d4"><div class="num" data-count="10" data-suffix="+">0</div><div class="lbl">метрик риска в портфельной аналитике</div></div>
      <div class="stat rv d4"><div class="num" data-count="3">0</div><div class="lbl">уровня обзора рынка</div></div>
    </div>
  </div>
</section>

<!-- WHY -->
<section class="band" id="why">
  <div class="wrap">
    <div class="sec-head">
      <div class="eyebrow rv">Зачем это нужно</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Анализировать самому — много работы, и на волатильном рынке она быстро устаревает</h2>
      <p class="lead rv d2">Полный разбор одной компании — это отчётность, мультипликаторы, отраслевой и макроконтекст, геополитика, по десяткам источников. На турбулентном рынке всё это меняется быстро. Базис собирает и обновляет полный контекст системно, по одной методике, со ссылками на источники — чтобы решение опиралось на полную и актуальную картину.</p>
    </div>
  </div>
</section>

<!-- METHOD -->
<section class="band band-alt" id="method">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">Методика оценки</div>
        <h3 class="rv d1">Шесть уровней анализа, каждый влияет на оценку</h3>
        <p class="rv d2">Бизнес-модель, финансы и оценка, корпоративное управление, рынок, макроэкономика, геополитика — шесть связанных уровней. Каждый влияет на итоговую справедливую цену по явной цепочке: цена Urals → денежный поток → дивиденд → оценка. Видна не только цифра, но и логика — с источником и допущениями под каждым шагом.</p>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Как складывается справедливая цена</span><span class="pv-tag tag-j">суждение</span></div>
          <div class="pv-levels">
            <div class="lvl-row"><span class="lvl-n">01</span><span class="lvl-t">Бизнес-модель</span><span class="lvl-b"><i style="width:64%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">02</span><span class="lvl-t">Финансы и оценка</span><span class="lvl-b"><i style="width:82%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">03</span><span class="lvl-t">Корп. управление</span><span class="lvl-b"><i style="width:48%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">04</span><span class="lvl-t">Рынок</span><span class="lvl-b"><i style="width:58%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">05</span><span class="lvl-t">Макроэкономика</span><span class="lvl-b"><i style="width:70%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">06</span><span class="lvl-t">Геополитика</span><span class="lvl-b"><i style="width:44%"></i></span></div>
          </div>
          <div class="cc-fv" style="margin-top:13px"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 1 · COMPANY ANALYSIS -->
<section class="band" id="analysis">
  <div class="wrap">
    <div class="sec-head" style="margin-bottom:44px">
      <div class="eyebrow rv">Возможности</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Единый процесс — от компании до портфеля</h2>
      <p class="lead rv d2">Базис закрывает весь процесс — разобрать компанию, найти идею, понять рынок, держать фон актуальным, оценить портфель.</p>
    </div>
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">01 — Анализ компаний</div>
        <h3 class="rv d1">Полный разбор компании со справедливой ценой</h3>
        <p class="rv d2">Семь разделов — обзор, бизнес-модель, финансы и оценка, корпоративное управление, рынок, макро, геополитика. Под каждым тезисом источник; в итоге справедливая цена и потенциал с прозрачной методикой и допущениями.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Справедливая цена и потенциал — с допущениями</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Эпистемические теги: факт · оценка · суждение</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Цепочки передачи: макро → денежный поток</li>
        </ul>
        <a class="feat-link" href="#" data-route="rosn">Открыть пример — Роснефть <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Карточка компании · «Что важно сейчас»</span><span class="pv-tag tag-j">суждение</span></div>
          <div class="pv-tabs"><span class="on">Обзор</span><span>Бизнес-модель</span><span>Финансы и оценка</span><span>Корп. управление</span><span>Анализ рынка</span><span>Макроэкономика</span><span>Геополитика</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div class="cc-m"><div class="l">Выручка LTM</div><div class="v">9,12 трлн ₽</div><div class="bar" style="margin-top:6px"><i style="width:72%;background:var(--pos)"></i></div></div>
            <div class="cc-m"><div class="l">EV / EBITDA</div><div class="v">3,4×</div><div class="bar" style="margin-top:6px"><i style="width:80%;background:var(--accent)"></i></div></div>
          </div>
          <div class="cc-fv" style="margin-top:10px"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
          <div class="cc-m" style="margin-top:10px"><div class="l">Цепочка передачи · Urals → дивиденд</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:8px;flex-wrap:wrap">
              <span class="pv-sub" style="background:var(--panel-2);border:1px solid var(--line);border-radius:6px;padding:4px 8px">Urals</span><span style="color:var(--ink-3)">→</span>
              <span class="pv-sub" style="background:var(--panel-2);border:1px solid var(--line);border-radius:6px;padding:4px 8px">выручка</span><span style="color:var(--ink-3)">→</span>
              <span class="pv-sub" style="background:var(--panel-2);border:1px solid var(--line);border-radius:6px;padding:4px 8px">EBITDA</span><span style="color:var(--ink-3)">→</span>
              <span class="pv-sub" style="background:var(--accent-soft);border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);border-radius:6px;padding:4px 8px;color:var(--accent)">дивиденд</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 2 · SCREENING -->
<section class="band band-alt" id="screening">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">02 — Скринер</div>
        <h3 class="rv d1">Отбор по фундаментальным критериям</h3>
        <p class="rv d2">Фильтры по мультипликаторам, доходности и риску — с распределением рынка под каждым критерием, композитным баллом Базиса 0–100 (с уровнем уверенности) и картой «оценка × качество».</p>
        <p class="rv d2">Отбор по фундаментальным критериям с распределением рынка под каждым фильтром, композитным баллом Базиса 0–100 и картой «оценка × качество».</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Композитный балл Базиса с уровнем уверенности</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Гистограмма распределения под каждым фильтром</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Карта «дёшево × качественно»</li>
        </ul>
        <a class="feat-link" href="#" data-route="screener">Открыть скринер <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--heat-c)"></span><span class="pv-t">Скринер · композитный балл</span><span class="pv-tag" style="background:var(--accent-soft);color:var(--accent)">7 из 20</span></div>
          <table class="pv-tbl">
            <thead><tr><th>Компания</th><th>P/E</th><th>EV/EBITDA</th><th>Дивид.</th><th>Балл</th></tr></thead>
            <tbody>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--heat-a) 18%,transparent);color:var(--heat-a)">ЛК</span><b>Лукойл</b><span class="tk2">LKOH</span></td><td>4,4×</td><td>2,6×</td><td>12,6%</td><td><span class="pv-score" style="background:var(--pos)">81</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--heat-a) 18%,transparent);color:var(--heat-a)">ТА</span><b>Татнефть</b><span class="tk2">TATN</span></td><td>5,2×</td><td>3,0×</td><td>13,1%</td><td><span class="pv-score" style="background:var(--pos)">80</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--heat-c) 20%,transparent);color:var(--heat-c)">СБ</span><b>Сбербанк</b><span class="tk2">SBER</span></td><td>4,1×</td><td class="na">—</td><td>10,8%</td><td><span class="pv-score" style="background:var(--accent)">78</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--violet) 20%,transparent);color:var(--violet)">НЛ</span><b>НЛМК</b><span class="tk2">NLMK</span></td><td>5,8×</td><td>3,8×</td><td>12,3%</td><td><span class="pv-score" style="background:var(--accent)">77</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--heat-a) 18%,transparent);color:var(--heat-a)">РО</span><b>Роснефть</b><span class="tk2">ROSN</span></td><td>5,0×</td><td>3,4×</td><td>10,4%</td><td><span class="pv-score" style="background:var(--accent)">74</span></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 3 · BONDS -->
<section class="band" id="bonds">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">03 — Облигации</div>
        <h3 class="rv d1">Доходность против риска — по каждому выпуску</h3>
        <p class="rv d2">Разбор облигаций с оценкой: компенсирует ли доходность принятый кредитный и рыночный риск. Видно, где премия оправдана, а где нет.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Спред к ОФЗ и премия за риск</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Рейтинг рынка против оценки Базиса</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Ожидаемые потери: PD × LGD</li>
        </ul>
        <a class="feat-link" href="#" data-route="companies">Открыть облигации <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--heat-d)"></span><span class="pv-t">Облигации · доходность vs риск</span><span class="pv-tag tag-e">оценка</span></div>
          <table class="pv-tbl">
            <thead><tr><th>Выпуск</th><th>YTM</th><th>Спред</th><th>Рейтинг</th><th>Риск</th></tr></thead>
            <tbody>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--pos) 18%,transparent);color:var(--pos)">Сб</span><b>Сбер 1Р</b><span class="tk2">AAA</span></td><td>16,8%</td><td>+90</td><td>AAA</td><td><span class="pv-score" style="background:var(--pos)">1</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--pos) 18%,transparent);color:var(--pos)">РЖ</span><b>РЖД 1Р</b><span class="tk2">AAA</span></td><td>17,4%</td><td>+150</td><td>AAA</td><td><span class="pv-score" style="background:var(--pos)">2</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--amber) 20%,transparent);color:var(--amber)">АФ</span><b>АФК Сист.</b><span class="tk2">AA-</span></td><td>21,2%</td><td>+520</td><td>AA-</td><td><span class="pv-score" style="background:var(--amber)">3</span></td></tr>
              <tr><td class="c0"><span class="pvmono" style="background:color-mix(in srgb,var(--neg) 20%,transparent);color:var(--neg)">Се</span><b>Сегежа</b><span class="tk2">BBB</span></td><td>28,5%</td><td>+1180</td><td>BBB</td><td><span class="pv-score" style="background:var(--neg)">5</span></td></tr>
            </tbody>
          </table>
          <div class="pv-sub" style="margin-top:10px">Балл риска 1–5 · премия оценена относительно кредитного риска</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 4 · MARKET -->
<section class="band" id="market">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">04 — Рынок</div>
        <h3 class="rv d1">Ситуация на рынке и её драйверы</h3>
        <p class="rv d2">Индекс, ширина рынка, что движет ценами сегодня, тепловая карта секторов. Акции, облигации, фьючерсы, фонды, валюта и металлы — в одном месте.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Драйверы дня: макро-факторы и их влияние на бумаги</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Карта рынка: размер — капитализация, цвет — движение</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Индексы: МосБиржи, полной доходности, РТС</li>
        </ul>
        <a class="feat-link" href="#" data-route="companies">Открыть рынок <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--heat-b)"></span><span class="pv-t">Обзор рынка · Индекс МосБиржи</span><span class="pv-tag tag-f">факт</span></div>
          <div class="pv-idx"><span class="lv">2 847,3</span><span class="pv-d up">▲ 0,62%</span></div>
          <div class="pv-breadth"><i style="background:var(--pos);flex:13"></i><i style="background:var(--ink-3);opacity:.4;flex:2"></i><i style="background:var(--neg);flex:7"></i></div>
          <div style="display:flex;gap:14px;font-size:11.5px;color:var(--ink-2)"><span><b class="mono" style="color:var(--pos)">13</b> растут</span><span><b class="mono" style="color:var(--neg)">7</b> падают</span><span style="margin-left:auto;color:var(--ink-3)">что движет: нефть ↑ · ставка →</span></div>
          <div class="pv-heat">
            <i style="background:#1F8A5B;grid-column:span 2;aspect-ratio:3">Нефтегаз +1,2</i>
            <i style="background:#3AA06B">Финансы</i><i style="background:#C2435E">Метал.</i><i style="background:#D98C3A">IT</i><i style="background:#5BA873">Хим.</i>
            <i style="background:#C2435E">Деве.</i><i style="background:#8A8275">Тел.</i><i style="background:#3AA06B">Энерг.</i><i style="background:#D98C3A">Ритейл</i><i style="background:#8A8275">Тран.</i>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 6 · PORTFOLIO -->
<section class="band band-alt" id="portfolio">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">06 — Портфельная аналитика</div>
        <h3 class="rv d1">Риск, корреляции, диверсификация, доходность</h3>
        <p class="rv d2">Анализ портфеля на метриках из корпоративных финансов: концентрация, бета, волатильность, альфа, матрица корреляций, структура рисков и сравнение с индексами полной доходности — того, чего нет в таблице брокера.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Концентрация, бета, волатильность, альфа</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Матрица корреляций и скрытые связи</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Сравнение с IMOEX и индексом полной доходности</li>
        </ul>
        <a class="feat-link" href="#" data-route="companies">Диагностика портфеля <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--pos)"></span><span class="pv-t">Портфель · здоровье и корреляции</span><span class="pv-tag" style="background:color-mix(in srgb,var(--amber) 14%,transparent);color:var(--amber)">риск ↑</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
            <div class="cc-m"><div class="l">Концентрация топ-3</div><div class="v" style="color:var(--amber)">38%</div></div>
            <div class="cc-m"><div class="l">Бета к индексу</div><div class="v">1,14</div></div>
          </div>
          <div class="pv-corr" id="pvCorr"></div>
          <div class="pv-sub" style="margin-top:8px">Матрица корреляций · 6 крупнейших позиций</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 5 · STRESS + 6 · OBSERVER (two-up) -->
<section class="band" id="observer">
  <div class="wrap">
    <div class="sec-head">
      <div class="eyebrow rv">Обозреватель · стресс-тест</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Рыночный фон и проверка на сценарии</h2>
      <p class="lead rv d2">Обозреватель — рыночный фон без чтения первоисточников: новости, макро, геополитика и отчётность кратко и по сути. Стресс-тест — что будет с портфелем при обвале нефти, росте ставки, укреплении рубля.</p>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:44px" class="two-up">
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--neg)"></span><span class="pv-t">07 · Стресс-тест · сценарии кризиса</span><span class="pv-tag" style="background:var(--violet-soft);color:var(--violet)">сценарий</span></div>
          <div class="pv-stress">
            <div class="pv-sb"><div class="sbh"><b>Обвал нефти до 45 $</b><span class="sv">−22%</span></div><div class="sbt"><i style="width:70%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>Рост ставки до 23%</b><span class="sv">−14%</span></div><div class="sbt"><i style="width:48%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>Укрепление рубля</b><span class="sv">−11%</span></div><div class="sbt"><i style="width:38%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>«Чёрный лебедь»</b><span class="sv">−35%</span></div><div class="sbt"><i style="width:92%"></i></div></div>
          </div>
        </div>
      </div>
      <div class="rv d3">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--violet)"></span><span class="pv-t">05 · Обозреватель · фон рынка</span><span class="pv-tag tag-e">оценка</span></div>
          <div class="pv-feed">
            <div class="pv-fi"><span class="lvl" style="background:var(--accent-soft);color:var(--accent)">экспресс</span><p>ЦБ сохранил ставку 18%; сигнал жёсткий — давление на оценки длинных активов.</p></div>
            <div class="pv-fi"><span class="lvl" style="background:color-mix(in srgb,var(--heat-b) 18%,transparent);color:var(--heat-d)">детальный</span><p>Нефть Urals +6% за неделю на фоне сокращения добычи ОПЕК+ — плюс экспортёрам.</p></div>
            <div class="pv-fi"><span class="lvl" style="background:var(--violet-soft);color:var(--violet)">глубокий AI</span><p>Геополитика: новые ограничения на логистику могут расширить дисконт Urals к Brent.</p></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 7 · ANALYST CONSENSUS -->
<section class="band band-alt">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">08 — Консилиум аналитиков</div>
        <h3 class="rv d1">Консенсус брокеров и позиция Базиса</h3>
        <p class="rv d2">Целевые цены ведущих аналитиков с разбросом, рядом — независимая позиция платформы с обоснованием. Видно, где Базис сходится с консенсусом, а где расходится.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Целевые цены брокеров с разбросом</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Независимая позиция Базиса с обоснованием</li>
        </ul>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Консилиум · целевые цены ROSN</span><span class="pv-tag" style="background:var(--accent-soft);color:var(--accent)">Базис</span></div>
          <div class="pv-cons">
            <div class="pv-cbar"><span class="lbl">Брокер А</span><span class="mk" style="left:42%;background:var(--ink-3)"></span></div>
            <div class="pv-cbar"><span class="lbl">Брокер Б</span><span class="mk" style="left:58%;background:var(--ink-3)"></span></div>
            <div class="pv-cbar"><span class="lbl">Брокер В</span><span class="mk" style="left:70%;background:var(--ink-3)"></span></div>
            <div class="pv-cbar" style="border-color:color-mix(in srgb,var(--accent) 40%,transparent)"><span class="lbl" style="color:var(--accent)">Базис · +18%</span><span class="bz" style="left:64%"></span></div>
          </div>
          <div class="pv-sub" style="margin-top:10px;line-height:1.5">Базис ближе к верхней границе консенсуса — основной аргумент: контроль капзатрат и потенциал «Восток Ойл».</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- DIFFERENTIATOR -->
<section class="band" id="trust-sec">
  <div class="wrap">
    <div class="sec-head diff-head">
      <div class="eyebrow rv">Методика и достоверность</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Каждое утверждение помечено уровнем достоверности</h2>
      <p class="lead rv d2">Не «магия ИИ», а прозрачная методика. Каждое утверждение помечено уровнем достоверности — вы всегда видите, на чём основан вывод.</p>
    </div>
    <div class="fej">
      <div class="fc rv" style="--c:var(--ink-3)"><div class="tg">Факт</div><h4>Подтверждён источником</h4><p>Отчётность, котировки, официальные данные — с датой и ссылкой.</p></div>
      <div class="fc rv d1" style="--c:var(--heat-d)"><div class="tg">Оценка</div><h4>Модельный расчёт</h4><p>Получено из модели с явными допущениями, которые можно проверить.</p></div>
      <div class="fc rv d2" style="--c:var(--accent)"><div class="tg">Суждение</div><h4>Интерпретация</h4><p>Аналитическое мнение, а не предсказание — с честными оговорками.</p></div>
      <div class="fc rv d3" style="--c:var(--violet)"><div class="tg">Сценарий</div><h4>Условный путь</h4><p>«Если X — тогда Y»: что должно произойти и что опровергнет вывод.</p></div>
    </div>
    <div class="pillars">
      <div class="pil rv"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg></div><div><h4>Прозрачная методика</h4><p>Источники, даты и допущения — видны или в одном клике.</p></div></div>
      <div class="pil rv d1"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 8v5l3 2"/></svg></div><div><h4>Полная картина</h4><p>Бизнес, риски, сценарии и портфельный контекст — а не один показатель.</p></div></div>
      <div class="pil rv d2"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg></div><div><h4>Независимость</h4><p>Не брокер, сделок не исполняем — нет конфликта интересов.</p></div></div>
    </div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section class="band band-alt">
  <div class="wrap">
    <div class="sec-head">
      <div class="eyebrow rv">Как читать анализ</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Четыре слоя — от компании до решения</h2>
    </div>
    <div class="layers">
      <div class="layer rv"><div class="ln">01</div><div class="lic"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6M9 13h4"/></svg></div><h4>Идентичность</h4><p>Кто это, чем занимается, как зарабатывает.</p></div>
      <div class="layer rv d1"><div class="ln">02</div><div class="lic"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6"/></svg></div><h4>Сигнал</h4><p>Что важно сейчас, тон и справедливая цена.</p></div>
      <div class="layer rv d2"><div class="ln">03</div><div class="lic"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg></div><h4>Доказательства</h4><p>Источники, надёжность и честные оговорки.</p></div>
      <div class="layer rv d3"><div class="ln">04</div><div class="lic"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></div><h4>Действие</h4><p>Проверка идеи и сценарии — перед решением.</p></div>
    </div>
  </div>
</section>

<!-- FINAL CTA -->
<section class="final">
  <div class="wrap">
    <div class="eyebrow rv">Начать</div>
    <h2 class="rv d1">Откройте платформу<br>или готовый разбор</h2>
    <p class="lead rv d2" style="margin:16px auto 0;text-align:center">Посмотрите анализ конкретной компании или зайдите в платформу целиком.</p>
    <div class="hero-actions rv d2">
      <a class="btn btn-primary btn-lg" href="#" data-route="companies">Открыть платформу →</a>
      <a class="btn btn-ghost btn-lg" href="#" data-route="rosn">Пример — Роснефть</a>
    </div>
  </div>
</section>

<footer>
  <div class="wrap">
    <a class="brand" href="#top"><span class="bm">B</span>Базис</a>
    <p class="fnote">© 2026 Платформа Базис · Не является индивидуальной инвестиционной рекомендацией. Независимый аналитический сервис — не брокер, сделок не исполняет.</p>
    <div class="flinks"><a href="#analysis">Возможности</a><a href="#trust-sec">Методика</a><a href="#" data-route="companies">Платформа</a></div>
  </div>
</footer>

<template id="__bundler_thumbnail" data-bg-color="#0B0D12">
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="#F4F1EA"/><rect x="34" y="30" width="32" height="40" rx="8" fill="url(#g)"/><text x="50" y="60" font-family="Georgia,serif" font-size="26" font-weight="700" fill="#fff" text-anchor="middle">B</text><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2347D9"/><stop offset="1" stop-color="#7A4DE0"/></linearGradient></defs></svg>
</template>

`;
export default LANDING_HTML;
