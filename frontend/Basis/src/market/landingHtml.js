// Лендинг v4. Структура — по брифу владельца (2026-07-30): не каталог фич, а разделы
// платформы, у каждого названа ценность. Копирайт переписан после разбора с советником:
// первая редакция была написана В РЕГИСТРЕ УГОВАРИВАНИЯ — субъектом текста был читатель
// и его дефициты («на один разбор уходят дни»), отсюда просторечие и рекламная
// парцелляция. Деловая аналитическая проза утверждает о ПРЕДМЕТЕ (рынок, метод,
// стоимость), а читатель узнаёт себя сам.
//
// 🔴 Сквозная мысль страницы — НЕ «мы экономим ваше время» (это умеет любой агрегатор),
// а «мы даём единую систему координат для рынка, на котором её нет»: одна методика на
// 264 компании и 3100 выпусков ⇒ числа сравнимы между собой. Дефицит внимания — следствие,
// а не причина, и звучит как факт о методе, а не как жалоба на читателя.
//
// Правила тона (нарушать = вернуться к первой редакции): утверждение о предмете, а не о
// читателе; деталь вместо эпитета (264 / 3100 / 7 / 75 — фактура, эпитеты не нужны);
// полные предложения без парцелляции; ЗАПРЕЩЕНЫ «на самом деле», «правда», «секрет»,
// «сбой» — риторика разоблачения; ограничения формулируются как принцип, а не как
// оправдание («не брокер: сделок не исполняем» — без «нам незачем вас торопить»).
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
      <h1 class="rv d1">Платформа поддержки<br><span class="grad">инвестиционных решений</span></h1>
      <p class="hero-sub rv d2">Базис берёт на себя сбор данных, анализ и расчёты по всему российскому рынку: 264 компании и 3100 выпусков облигаций по единой методике — от финансовой отчётности до геополитики, корпоративного управления и институциональных особенностей. Платформа показывает справедливую стоимость бумаг и риски, которые не видны в котировках, — вам остаётся ознакомиться с выводами и принять решение. Мы не брокер: сделок не исполняем и торговых сигналов не даём.</p>
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

<!-- TRUST BAND -->
<section class="trust">
  <div class="wrap">
    <div class="trust-grid">
      <div class="stat rv"><div class="num" data-count="264">0</div><div class="lbl">компаний, разобранных по единой методике</div></div>
      <div class="stat rv d1"><div class="num" data-count="3000" data-suffix="+">0</div><div class="lbl">выпусков облигаций: доходность против&nbsp;риска</div></div>
      <div class="stat rv d2"><div class="num" data-count="7">0</div><div class="lbl">связанных разделов анализа по компании</div></div>
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
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">Готовый анализ вместо самостоятельного поиска</h2>
      <p class="lead rv d2">Обоснованное решение по одной бумаге требует изучить отчётность, оценить долговую нагрузку и дивиденды, учесть макроэкономику, геополитику, качество корпоративного управления и институциональные особенности эмитента. Базис выполняет эту работу системно, по всему рынку и по единой методике: вы открываете готовый разбор с выводами и справедливой ценой — и видите в том числе риски, о которых не знали, что их нужно искать. Результат — меньше ошибочных решений, устойчивее доходность на сложном рынке и время, потраченное на выбор, а не на сбор данных.</p>
    </div>
  </div>
</section>

<!-- 01 · MARKET + COMPANY CARD -->
<section class="band band-alt" id="market">
  <div class="wrap">
    <div class="sec-head" style="margin-bottom:44px">
      <div class="eyebrow rv">Состав платформы</div>
      <h2 class="sh rv d1" style="margin-left:auto;margin-right:auto">От отдельной бумаги до устойчивости портфеля</h2>
      <p class="lead rv d2">Разбор компании, рыночный контекст, отбор кандидатов, структура риска и проверка портфеля на сценариях — в одном контуре и по одной методике. Каждый раздел сокращает путь от информации к обоснованному решению.</p>
    </div>
    <div class="feat">
      <div class="feat-copy">
        <div class="feat-num rv">01 — Рынок</div>
        <h3 class="rv d1">Готовая аналитика и выводы по каждой бумаге</h3>
        <p class="rv d2">Акции, облигации, фьючерсы, фонды, валюта и металлы. По каждой компании — семь связанных разделов анализа: бизнес-модель, финансы и оценка, корпоративное управление, рынки присутствия, макроэкономика, геополитика и институциональная среда. Разделы не соседствуют, а входят друг в друга: вывод одного становится параметром расчёта в другом. Под каждым утверждением — источник и его статус: факт, оценка или суждение.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Справедливая цена с раскрытой выкладкой и допущениями</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Семь связанных разделов вместо разрозненных источников</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Котировка и мультипликаторы пересчитываются непрерывно — оценка не привязана к дате разбора</li>
        </ul>
        <a class="feat-link" href="#" data-route="rosn">Открыть пример — Роснефть <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg></a>
      </div>
      <div class="rv d2">
        <div class="pv">
          <div class="pv-h"><span class="pv-dot" style="background:var(--accent)"></span><span class="pv-t">Карточка компании · Роснефть</span><span class="pv-tag tag-j">суждение</span></div>
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
        <p class="rv d2">Высокий купон сам по себе не информативен: значение имеет то, компенсирует ли он кредитный риск эмитента и переоценку выпуска при изменении ставки. Базис оценивает это по каждой бумаге — где премия соответствует принимаемому риску, а где инвестору платят за риск, которого он не учёл.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Спред к ОФЗ против кредитного качества эмитента</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Рейтинг агентства рядом с собственной оценкой платформы</li>
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
        <h3 class="rv d1">Классическая модель оценки не знает, в какой стране торгуется бумага</h3>
        <p class="rv d2">Дисконтная модель исходит из допущения, что заработанное компанией дойдёт до акционера. На российском рынке это допущение слишком сильное: между прибылью и дивидендом стоят структура собственности и её отношения с государством, санкционный контур, геополитическая траектория и стоимость денег. Базис оценивает поток, который достаётся миноритарию, — дивидендная модель, где институциональная среда, качество корпоративного управления и макроэкономический режим входят параметрами расчёта, а не оговоркой под таблицей: слабое корпоративное управление повышает требуемую доходность и тем самым снижает справедливую цену.</p>
        <p class="rv d2">Модель намеренно консервативна — она требует премии к доходности ОФЗ и потому выделяет бумаги с запасом прочности. Знание стоимости защищает от переплаты, дисциплина метода — от настроения рынка.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Институты, геополитика и макроэкономика — параметры расчёта, а не комментарий к нему</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Премия к доходности ОФЗ как порог: ниже него бумага не проходит отбор</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>По 75 компаниям из 264 модель не даёт числа — и объясняет причину</li>
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
          <div class="pv-sub" style="margin-top:10px;line-height:1.5">Каждый уровень изменяет либо требуемую доходность, либо сам поток — и потому смещает итоговую цену.</div>
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
        <h3 class="rv d1">Рыночный контекст в готовом виде</h3>
        <p class="rv d2">Лента, календарь событий и обзоры рынка закрывают вопрос осведомлённости. Существеннее другое: в момент публикации отчётности вы получаете не первичный документ, а его разбор — что показал отчёт, что изменилось против предыдущего периода и какие статьи это объясняют.</p>
        <p class="rv d2">Отдельный слой — состояние макроэкономической, геополитической и институциональной среды: в какую сторону движется контекст и каких секторов это коснётся. ИИ-отчёт собирает эту картину применительно к составу вашего портфеля.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Разбор отчётности в момент публикации — вместо первичного документа</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Макроэкономика, геополитика и институты — как направление среды, а не поток новостей</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>ИИ-отчёт: рыночный контекст, соотнесённый с составом портфеля</li>
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
        <h3 class="rv d1">Сопоставление бумаг в единой системе координат</h3>
        <p class="rv d2">Фильтры по мультипликаторам, доходности и риску сопровождаются распределением рынка по каждому критерию — чтобы «дёшево» определялось относительно всей совокупности, а не соседней бумаги. Композитный балл 0–100 приводится с уровнем уверенности, а карта «оценка × качество» показывает обе координаты одновременно.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Композитный балл с указанием уровня уверенности</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Распределение рынка под каждым критерием отбора</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Карта «оценка × качество» — обе координаты одновременно</li>
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
        <h3 class="rv d1">Скрытые связи и системные риски портфеля</h3>
        <p class="rv d2">Брокерский отчёт показывает результат. Он не показывает, что три позиции движутся синхронно, что портфель вдвое чувствительнее рынка и что годовой результат обеспечен одной бумагой. Базис считает концентрацию, бету, волатильность, альфу и матрицу корреляций и сопоставляет портфель с индексом полной доходности — то есть с учётом дивидендов, а не одной цены.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Концентрация, бета, волатильность, альфа</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Матрица корреляций: связи, не видимые в списке позиций</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Индекс качества портфеля: на чём он держится и где уязвим</li>
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
        <h3 class="rv d1">Как портфель поведёт себя при сдвиге нефти, ставки и курса</h3>
        <p class="rv d2">Сценарии — от сдвига нефти, ставки и курса до «чёрного лебедя» — рассчитываются по факторной модели, а не оцениваются приблизительно: видна и глубина просадки, и вклад каждой позиции в неё. Неопределённость становится величиной, с которой можно работать до того, как сценарий реализуется.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Шоки по нефти, ставке и курсу — по отдельности и совокупно</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Вклад каждой позиции в просадку</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Оценённая величина риска вместо предположения о нём</li>
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
        <h3 class="rv d1">Ассистент, обученный на аналитике платформы</h3>
        <p class="rv d2">«Что происходит с моим портфелем», «разбери Сбербанк», «какие отчётности выходят на следующей неделе». Отвечает не обёртка над публичной языковой моделью, а агент, работающий на данных и методике Базиса: каждое утверждение — с указанием статуса достоверности и ссылкой на раздел-источник, состав вашего портфеля учитывается в ответе.</p>
        <ul class="feat-pts rv d2">
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Ответ строится на данных платформы, а не на памяти модели</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Каждое утверждение — со ссылкой на источник</li>
          <li><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>Учитывает состав портфеля при ответе</li>
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
    <div class="pillars">
      <div class="pil rv"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg></div><div><h4>Единая методика</h4><p>Один метод для всего рынка: числа сравнимы между собой.</p></div></div>
      <div class="pil rv d1"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 8v5l3 2"/></svg></div><div><h4>Полнота картины</h4><p>Бизнес, риски, сценарии и портфельный контекст вместо отдельного показателя.</p></div></div>
      <div class="pil rv d2"><div class="pic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg></div><div><h4>Независимость</h4><p>Мы не брокер: сделок не исполняем и торговых сигналов не даём.</p></div></div>
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
    <div class="flinks"><a href="#market">Возможности</a><a href="#method">Методика</a><a href="#" data-route="companies">Платформа</a></div>
  </div>
</footer>

`;
export default LANDING_HTML;
