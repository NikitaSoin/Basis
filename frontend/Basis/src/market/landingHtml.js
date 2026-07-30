// Лендинг v4. Структура и копирайт — по брифу владельца (2026-07-30): не каталог
// фич, а разделы платформы, у каждого явно названа ЦЕННОСТЬ для инвестора. Сквозная
// линия, которая держит всю страницу: у частного инвестора нет времени на разбор,
// нам можно доверять (не брокер, сделок не исполняем), мы помогаем разобраться и
// показываем, сколько бумага стоит на самом деле — чтобы сохранить капитал.
//
// Порядок разделов задан владельцем: Рынок (акции + облигации) → методика
// справедливой цены → Обозреватель → Скринер → Портфель → Стресс-тест → Ассистент.
//
// 🔴 Методику НЕ раскрываем целиком (решение владельца): показываем только, что она
// сложнее классической — dividend discounted model, в которую заложены оценка
// институциональной среды, геополитических трендов и влияние макроэкономики.
//
// Разметка в словаре styles/landing.css (band/feat/pv/rv…), CTA → data-route
// (роутинг в LandingNeo). Карточка в hero и бегущая строка — ЖИВЫЕ (LandingNeo
// подтягивает котировки и метрики каждые 8с), это не мокап.
const LANDING_HTML = `

<span id="top"></span>
<!-- HERO -->
<section class="hero">
  <div class="hero-bg"><canvas id="heat"></canvas><div class="mesh"></div><div class="mesh v"></div></div>
  <div class="wrap">
    <div>
      <div class="hero-badge rv"><i></i> Независимая аналитика российского рынка · второе мнение перед решением</div>
      <h1 class="rv d1">Сколько на самом деле<br><span class="grad">стоят ваши акции</span></h1>
      <p class="hero-sub rv d2">Полный разбор одной компании — это несколько дней работы по десяткам источников, и через неделю половина устаревает. Базис держит эту работу сделанной по всему рынку: разбор каждой бумаги, рыночный фон, справедливая цена по своей методике и проверка портфеля на прочность. Мы не брокер и сделок не исполняем — нам незачем вас торопить.</p>
      <div class="hero-actions rv d3">
        <a class="btn btn-primary btn-lg" href="#" data-route="companies">Открыть платформу →</a>
        <a class="btn btn-ghost btn-lg" href="#" data-route="rosn">Пример — Роснефть</a>
      </div>
      <div class="qlinks rv d4">
        <a href="#market"><span class="qd" style="background:var(--accent)"></span>Рынок</a>
        <a href="#method"><span class="qd" style="background:var(--heat-d)"></span>Справедливая цена</a>
        <a href="#observer"><span class="qd" style="background:var(--pos)"></span>Обозреватель</a>
        <a href="#portfolio"><span class="qd" style="background:var(--amber)"></span>Портфель</a>
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
          <div class="cc-live"><span class="cc-live-dot"></span>числа живые — пересчитываются, пока вы читаете</div>
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
      <div class="stat rv"><div class="num" data-count="264">0</div><div class="lbl">компаний с полным разбором</div></div>
      <div class="stat rv d1"><div class="num" data-count="3000" data-suffix="+">0</div><div class="lbl">облигаций: доходность против&nbsp;риска</div></div>
      <div class="stat rv d2"><div class="num" data-count="7">0</div><div class="lbl">разделов разбора по каждой компании</div></div>
      <div class="stat rv d3"><div class="num mono">0–100</div><div class="lbl">композитный балл в скринере</div></div>
      <div class="stat rv d4"><div class="num" data-count="10" data-suffix="+">0</div><div class="lbl">метрик риска в аналитике портфеля</div></div>
      <div class="stat rv d4"><div class="num" data-count="4">0</div><div class="lbl">сценария стресс-теста портфеля</div></div>
    </div>
  </div>
</section>

<!-- WHY -->
<section class="band" id="why">
  <div class="wrap">
    <div class="sec-head">
      <div class="eyebrow rv">Зачем это нужно</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">На один толковый разбор уходят дни. А их нужны десятки.</h2>
      <p class="lead rv d2">Отчётность, мультипликаторы, отрасль, макроэкономика, геополитика, институциональная среда, риск бумаги в вашем портфеле — по десяткам источников и с разной свежестью. Через неделю половина уже неактуальна. Базис держит эту работу сделанной по всему рынку сразу и обновляет её без вас — чтобы ваше время уходило на решение, а не на сбор данных.</p>
    </div>
  </div>
</section>

<!-- 01 · MARKET + COMPANY CARD -->
<section class="band band-alt" id="market">
  <div class="wrap">
    <div class="sec-head" style="margin-bottom:44px">
      <div class="eyebrow rv">Что внутри</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Весь процесс — от одной бумаги до всего портфеля</h2>
      <p class="lead rv d2">Разобрать компанию, понять фон рынка, найти идею, проверить портфель и его устойчивость. Всё в одном месте и по одной методике.</p>
    </div>
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">01 — Рынок</div>
        <h3 class="rv d1">Весь рынок — и полный разбор под каждой бумагой</h3>
        <p class="rv d2">Акции, облигации, фьючерсы, фонды, валюта и металлы. По каждой компании — семь разделов разбора: бизнес-модель, финансы и оценка, корпоративное управление, рынки, макроэкономика, геополитика и институциональная среда. Под каждым тезисом источник и пометка, факт это, оценка или суждение.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Справедливая цена и потенциал — с допущениями, а не одним числом</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Семь разделов вместо десяти вкладок в браузере</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Цена и мультипликаторы живые — ничего не застывает на дате разбора</li>
        </ul>
        <a class="feat-link" href="#" data-route="rosn">Открыть пример — Роснефть <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Карточка компании · «Что важно сейчас»</span><span class="pv-tag tag-j">суждение</span></div>
          <div class="pv-tabs"><span class="on">Обзор</span><span>Бизнес-модель</span><span>Финансы и оценка</span><span>Корп. управление</span><span>Анализ рынка</span><span>Макроэкономика</span><span>Геополитика</span><span>Институты</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div class="cc-m"><div class="l">Выручка LTM</div><div class="v">9,12 трлн ₽</div><div class="bar" style="margin-top:6px"><i style="width:72%;background:var(--pos)"></i></div></div>
            <div class="cc-m"><div class="l">EV / EBITDA</div><div class="v">3,4×</div><div class="bar" style="margin-top:6px"><i style="width:80%;background:var(--accent)"></i></div></div>
          </div>
          <div class="cc-fv" style="margin-top:10px"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
          <div class="cc-m" style="margin-top:10px"><div class="l">Цепочка передачи · Urals → дивиденд</div>
            <div class="chain">
              <span class="ch-n">Urals</span><span class="ch-a">→</span>
              <span class="ch-n">выручка</span><span class="ch-a">→</span>
              <span class="ch-n">EBITDA</span><span class="ch-a">→</span>
              <span class="ch-n ch-end">дивиденд</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 01b · BONDS -->
<section class="band" id="bonds">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">01 — Рынок · облигации</div>
        <h3 class="rv d1">Главный вопрос по облигации — не доходность, а оправдана ли она риском</h3>
        <p class="rv d2">Высокий купон сам по себе ничего не значит: важно, компенсирует ли он кредитный риск эмитента и переоценку по ставке. Базис считает это по каждому выпуску — видно, где премия честная, а где вам платят за риск, который вы не заметили.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Спред к ОФЗ против кредитного качества эмитента</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Рейтинг агентств против собственной оценки Базиса</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Чувствительность к ставке и ожидаемые потери</li>
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

<!-- 02 · FAIR VALUE METHOD -->
<section class="band band-alt" id="method">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">02 — Справедливая цена</div>
        <h3 class="rv d1">Старые методики на российском рынке дают сбой</h3>
        <p class="rv d2">Классическая модель исходит из того, что заработанное компанией дойдёт до акционера. В России между прибылью и вашим дивидендом стоит слишком многое: кто собственник и как он связан с государством, санкционный контур, геополитика, ставка ЦБ. Поэтому мы считаем не прибыль, а поток, который реально доходит до миноритария, — dividend discounted model, в которую заложены оценка институциональной среды, геополитических трендов и влияние макроэкономики.</p>
        <p class="rv d2">Такая модель намеренно осторожна: она требует за риск доходность выше ОФЗ и потому отбирает бумаги, которые достаточно безопасны для вложения. Это не про то, чтобы поймать максимум, — это про то, чтобы сохранить капитал.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Институты, геополитика и макро — не текстом рядом, а поправкой в самом расчёте</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Порог доходности выше ОФЗ — иначе бумага его не проходит</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Где модель неприменима — она честно не даёт числа и говорит почему</li>
        </ul>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Что входит в справедливую цену</span><span class="pv-tag tag-j">суждение</span></div>
          <div class="pv-levels">
            <div class="lvl-row"><span class="lvl-n">01</span><span class="lvl-t">Бизнес-модель</span><span class="lvl-b"><i style="width:64%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">02</span><span class="lvl-t">Финансы и оценка</span><span class="lvl-b"><i style="width:82%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">03</span><span class="lvl-t">Корп. управление</span><span class="lvl-b"><i style="width:48%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">04</span><span class="lvl-t">Рынки компании</span><span class="lvl-b"><i style="width:58%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">05</span><span class="lvl-t">Макроэкономика</span><span class="lvl-b"><i style="width:70%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">06</span><span class="lvl-t">Геополитика</span><span class="lvl-b"><i style="width:44%"></i></span></div>
            <div class="lvl-row"><span class="lvl-n">07</span><span class="lvl-t">Институциональная среда</span><span class="lvl-b"><i style="width:52%"></i></span></div>
          </div>
          <div class="cc-fv" style="margin-top:13px"><span class="fvl">Справедливая<br>цена</span><span class="fvbar"><i></i></span><span class="fvv">+18%</span></div>
          <div class="pv-sub" style="margin-top:10px;line-height:1.5">Каждый уровень меняет требуемую доходность или сам поток — и потому двигает итоговую цену.</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 03 · OBSERVER -->
<section class="band" id="observer">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">03 — Обозреватель</div>
        <h3 class="rv d1">Рыночный фон без чтения первоисточников</h3>
        <p class="rv d2">Лента новостей, обзоры рынка и календарь событий — чтобы ничего не пропустить. Главное: как только выходит отчётность, вы получаете не двести страниц PDF, а готовый разбор — что показал отчёт и что в нём изменилось против прошлого раза.</p>
        <p class="rv d2">Отдельно — оценка макроэкономической, геополитической и институциональной ситуации: куда всё движется глобально и как это отразится на российском рынке. И ИИ-отчёт, который за пару минут собирает весь рыночный контекст с учётом именно вашего портфеля.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Готовые разборы отчётностей — ничего не упускаете и сразу понимаете суть</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Макро, геополитика и институты — куда движется среда и кого это заденет</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>ИИ-отчёт за пару минут — рыночный контекст под ваш портфель</li>
        </ul>
        <a class="feat-link" href="#" data-route="overview">Открыть обозреватель <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--violet)"></span><span class="pv-t">Обозреватель · фон рынка</span><span class="pv-tag tag-e">оценка</span></div>
          <div class="pv-feed">
            <div class="pv-fi"><span class="lvl" style="background:var(--accent-soft);color:var(--accent)">отчётность</span><p>Вышел отчёт за полугодие: прибыль +16% г/г при росте процентного дохода на 18% — разбор готов, читать PDF не нужно.</p></div>
            <div class="pv-fi"><span class="lvl" style="background:color-mix(in srgb,var(--heat-b) 18%,transparent);color:var(--heat-d)">макро</span><p>ЦБ сохранил ставку; сигнал жёсткий — давление на оценки длинных активов сохраняется.</p></div>
            <div class="pv-fi"><span class="lvl" style="background:var(--violet-soft);color:var(--violet)">ИИ-отчёт</span><p>По вашему портфелю: две трети в экспортёрах, укрепление рубля — главный сквозной риск недели.</p></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 04 · SCREENER -->
<section class="band band-alt" id="screening">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">04 — Скринер</div>
        <h3 class="rv d1">От всего рынка к десятку кандидатов за минуты</h3>
        <p class="rv d2">Фильтры по мультипликаторам, доходности и риску — с распределением рынка под каждым критерием, чтобы было видно, дёшево ли это на самом деле или только на фоне соседа. Плюс композитный балл Базиса 0–100 с уровнем уверенности и карта «оценка × качество».</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Композитный балл с честным уровнем уверенности</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Распределение рынка под каждым фильтром</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Карта «дёшево × качественно» — и то, и другое сразу</li>
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

<!-- 05 · PORTFOLIO -->
<section class="band" id="portfolio">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">05 — Аналитика портфеля</div>
        <h3 class="rv d1">Из чего на самом деле складывается ваш риск</h3>
        <p class="rv d2">Таблица брокера показывает, сколько вы заработали. Она не показывает, что три ваши бумаги ходят вместе, что портфель вдвое чувствительнее рынка и что весь результат года дала одна позиция. Базис считает концентрацию, бету, волатильность, альфу, матрицу корреляций и сравнивает вас с индексом полной доходности — с учётом дивидендов, а не только цены.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Концентрация, бета, волатильность, альфа</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Матрица корреляций и скрытые связи между позициями</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Индекс качества портфеля и ИИ-диагноз: щит и уязвимости</li>
        </ul>
        <a class="feat-link" href="#" data-route="portfolio">Открыть портфель <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
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

<!-- 06 · STRESS TEST -->
<section class="band band-alt" id="stress">
  <div class="wrap">
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">06 — Стресс-тестирование</div>
        <h3 class="rv d1">Узнать цену ошибки заранее, а не в день падения</h3>
        <p class="rv d2">Что станет с вашим портфелем, если нефть уйдёт к 45 долларам, ставка вырастет ещё, рубль укрепится или случится сценарий, которого никто не ждал. Сценарии считаются по факторной модели, а не «на глаз», — видно и глубину просадки, и какая позиция тянет вниз сильнее всех.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Шоки по нефти, ставке и курсу — и совокупный удар</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Вклад каждой позиции в просадку</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Заранее понятная цена риска — основа сохранения капитала</li>
        </ul>
        <a class="feat-link" href="#" data-route="stress">Открыть стресс-тест <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--neg)"></span><span class="pv-t">Стресс-тест · сценарии кризиса</span><span class="pv-tag" style="background:var(--violet-soft);color:var(--violet)">сценарий</span></div>
          <div class="pv-stress">
            <div class="pv-sb"><div class="sbh"><b>Обвал нефти до 45 $</b><span class="sv">−22%</span></div><div class="sbt"><i style="width:70%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>Рост ставки до 23%</b><span class="sv">−14%</span></div><div class="sbt"><i style="width:48%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>Укрепление рубля</b><span class="sv">−11%</span></div><div class="sbt"><i style="width:38%"></i></div></div>
            <div class="pv-sb"><div class="sbh"><b>«Чёрный лебедь»</b><span class="sv">−35%</span></div><div class="sbt"><i style="width:92%"></i></div></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 07 · ASSISTANT -->
<section class="band" id="assistant">
  <div class="wrap">
    <div class="feat rev">
      <div class="feat-copy">
        <div class="feat-num rv">07 — Ассистент</div>
        <h3 class="rv d1">Спросить словами — вместо поиска по разделам</h3>
        <p class="rv d2">«Что с моим портфелем», «разбери Сбер», «что было на рынке за неделю», «какие отчёты выходят на следующей неделе». Ассистент отвечает по данным самой платформы — с теми же пометками достоверности и ссылками на разделы, откуда взят каждый вывод.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Отвечает по данным платформы, а не по памяти модели</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Видит ваш портфель и отвечает с учётом него</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Не нужно знать, где что лежит на платформе</li>
        </ul>
        <a class="feat-link" href="#" data-route="ai">Открыть ассистента <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--heat-b)"></span><span class="pv-t">Ассистент · диалог</span><span class="pv-tag tag-e">оценка</span></div>
          <div class="chat">
            <div class="ch-q">Что сейчас главное по моему портфелю?</div>
            <div class="ch-r">
              <p>Две трети веса — экспортёры, поэтому крепкий рубль бьёт по вам сильнее, чем по рынку: бета к курсу выше единицы. <span class="tag tag-e">оценка</span></p>
              <p>Ближайшее событие — отчёт одной из позиций на следующей неделе, он же ваш крупнейший вес. <span class="tag tag-f">факт</span></p>
              <div class="ch-src">Источники: Портфель · Обозреватель · Календарь</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- DIFFERENTIATOR -->
<section class="band band-alt" id="trust-sec">
  <div class="wrap">
    <div class="sec-head diff-head">
      <div class="eyebrow rv">Почему нам можно верить</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Каждое утверждение помечено уровнем достоверности</h2>
      <p class="lead rv d2">Не «магия ИИ», а прозрачная логика. Вы всегда видите, на чём основан вывод — и где мы честно не знаем.</p>
    </div>
    <div class="fej">
      <div class="fc rv" style="--c:var(--ink-3)"><div class="tg">Факт</div><h4>Подтверждён источником</h4><p>Отчётность, котировки, официальные данные — с датой и ссылкой.</p></div>
      <div class="fc rv d1" style="--c:var(--heat-d)"><div class="tg">Оценка</div><h4>Модельный расчёт</h4><p>Получено из модели с явными допущениями, которые можно проверить.</p></div>
      <div class="fc rv d2" style="--c:var(--accent)"><div class="tg">Суждение</div><h4>Интерпретация</h4><p>Аналитическое мнение, а не предсказание — с честными оговорками.</p></div>
      <div class="fc rv d3" style="--c:var(--violet)"><div class="tg">Сценарий</div><h4>Условный путь</h4><p>«Если X — тогда Y»: что должно произойти и что опровергнет вывод.</p></div>
    </div>
    <div class="pillars">
      <div class="pil rv"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg></div><div><h4>Экономим ваше время</h4><p>Разбор уже сделан и обновляется сам — вам остаётся решение.</p></div></div>
      <div class="pil rv d1"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 8v5l3 2"/></svg></div><div><h4>Полная картина</h4><p>Бизнес, риски, сценарии и портфельный контекст — а не один показатель.</p></div></div>
      <div class="pil rv d2"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg></div><div><h4>Независимость</h4><p>Не брокер, сделок не исполняем — нам незачем вас торопить.</p></div></div>
    </div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section class="band">
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
    <h2 class="rv d1">Решение принимаете вы.<br>Разбор — за нами</h2>
    <p class="lead rv d2" style="margin:16px auto 0;text-align:center">Откройте готовый разбор конкретной компании или зайдите в платформу целиком.</p>
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
    <div class="flinks"><a href="#market">Возможности</a><a href="#method">Методика</a><a href="#" data-route="companies">Платформа</a></div>
  </div>
</footer>

`;
export default LANDING_HTML;
