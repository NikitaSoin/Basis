// Basis Market — tab renderers. Exported to window.
const { useState: useStateM, useMemo: useMemoM } = React;

// shared bits
function Delta({ pct, abs }){
  const cls = pct>0?"up":pct<0?"dn":"fl";
  const g = pct>0?"▲":pct<0?"▼":"▬";
  return (
    <span className={"mk-delta "+cls}>
      {abs!=null && <span className="mk-delta-abs">{pct>0?"+":""}{window.mkNum(abs,2)}{NB}₽</span>}
      <span className="mk-delta-pct">{g} {window.mkNum(Math.abs(pct),2)}{NB}%</span>
    </span>
  );
}
const NB="\u00A0";
function Mono({ t, sec, big }){
  return <span className={"mk-mono"+(big?" lg":"")} style={{background:(window.MK_SECTOR_COLORS[sec]||"var(--accent)")+"22", color:window.MK_SECTOR_COLORS[sec]||"var(--accent)"}}>{t.slice(0,2)}</span>;
}
function ConfDots({ level }){
  const n = level==="high"?3:level==="medium"?2:1;
  return <span className="mk-conf" title={"Уверенность Basis: "+(level==="high"?"высокая":level==="medium"?"средняя":"низкая")}>{[0,1,2].map(i=><i key={i} className={i<n?"on":""}/>)}</span>;
}

// ===================== STOCKS =====================
function ToneChip({ tone, conf }){
  const fv=Math.round((tone-58)*0.85);
  const c=window.mkFvColor(fv);
  return (
    <span className="mk-tone" title="Потенциал к справедливой стоимости (оценка Basis) — не рекомендация">
      <span className="mk-tone-dot" style={{background:c}}/>
      <span className="mk-tone-l" style={{color:c}}>{fv>0?"+":""}{fv}%</span>
      <span className="mk-tone-cap">к справедл.</span>
      <ConfDots level={conf}/>
    </span>
  );
}
function StockCard({ s, onOpen }){
  return (
    <button className="mk-card" onClick={()=>onOpen(s)}>
      <div className="mk-card-top">
        <Mono t={s.t} sec={s.sec}/>
        <div className="mk-card-id">
          <b>{s.n}</b>
          <span className="mk-card-tk">{s.t} · {s.sec}</span>
        </div>
      </div>
      <div className="mk-card-px">
        <span className="mk-card-price">{window.mkNum(s.price,2)}<span className="mk-cur"> ₽</span></span>
        <Delta pct={s.chg} abs={s.chgAbs}/>
      </div>
      <div className="mk-card-foot">
        <span className="mk-cap">{window.mkMoney(s.mcap)}</span>
        <ToneChip tone={s.tone} conf={s.conf}/>
      </div>
    </button>
  );
}
function StocksTab({ query, sector, onOpen }){
  const rows = window.MK_STOCKS.filter(s=>
    (sector==="Все"||s.sec===sector) &&
    (!query || (s.n+" "+s.t).toLowerCase().includes(query.toLowerCase()))
  );
  const groups = {};
  rows.forEach(s=>{ (groups[s.sec]=groups[s.sec]||[]).push(s); });
  const order = window.MK_STOCK_SECTORS.filter(g=>groups[g]);
  if(rows.length===0) return <div className="mk-empty">Ничего не найдено. Измените запрос или сектор.</div>;
  return (
    <div className="mk-stack">
      {order.map(g=>(
        <section key={g}>
          <div className="mk-grp-head"><span className="mk-grp-dot" style={{background:window.MK_SECTOR_COLORS[g]}}/>{g}<span className="mk-grp-n">{groups[g].length}</span></div>
          <div className="mk-grid">{groups[g].map(s=><StockCard key={s.t} s={s} onOpen={onOpen}/>)}</div>
        </section>
      ))}
    </div>
  );
}

// ===================== BONDS =====================
function ReliBadge({ k }){ const r=window.MK_BOND_RELI[k]; return <span className={"mk-badge mk-badge-"+r.tone}>{r.label}</span>; }
const BOND_RATING={AAA:1,"AA+":2,AA:3,"AA-":4,"A+":5,A:6,"A-":7,"BBB+":8,BBB:9,"BB+":10,BB:11,"BB-":12,"B+":13,B:14};
const RELI_COLOR={ high:"var(--pos)", mid:"var(--amber)", vdo:"var(--neg)" };
function bondRisk(b){ return BOND_RATING[b.agency] ?? 9; }
function bondFair(r){ return 13.6 + 0.92*(r-1); } // справедливая доходность за риск

// Risk–reward map: rating (X) × YTM (Y), with a fair-compensation line.
function BondMap({ rows }){
  const W=820,H=440,padL=64,padR=88,padT=30,padB=54;
  const xMin=0.5,xMax=14.5,yMin=12,yMax=29;
  const X=v=>padL+(Math.max(xMin,Math.min(xMax,v))-xMin)/(xMax-xMin)*(W-padL-padR);
  const Y=v=>H-padB-(Math.max(yMin,Math.min(yMax,v))-yMin)/(yMax-yMin)*(H-padT-padB);
  const ticks=[["AAA",1],["AA",3],["A",6],["BBB",9],["BB",11],["B",14]];
  const yt=[14,18,22,26];
  return (
    <div className="mk-bondmap">
      <svg viewBox={`0 0 ${W} ${H}`} className="mk-bondmap-svg" preserveAspectRatio="xMidYMid meet">
        {yt.map(v=><g key={v}><line x1={padL} y1={Y(v)} x2={W-padR} y2={Y(v)} className="mk-bm-grid"/><text x={padL-10} y={Y(v)+4} className="mk-bm-tick" textAnchor="end">{v}%</text></g>)}
        {ticks.map(([l,v])=><text key={l} x={X(v)} y={H-padB+20} className="mk-bm-tick" textAnchor="middle">{l}</text>)}
        {/* fair line */}
        <line x1={X(xMin)} y1={Y(bondFair(xMin))} x2={X(xMax)} y2={Y(bondFair(xMax))} className="mk-bm-fair"/>
        <text x={X(xMax)} y={Y(bondFair(xMax))-8} className="mk-bm-fairlbl" textAnchor="end">справедливо за риск</text>
        {/* axis titles */}
        <text x={(padL+W-padR)/2} y={H-12} className="mk-bm-axis" textAnchor="middle">Кредитный риск · рейтинг (надёжнее ← → рискованнее)</text>
        <text x={18} y={(padT+H-padB)/2} className="mk-bm-axis" textAnchor="middle" transform={`rotate(-90 18 ${(padT+H-padB)/2})`}>Доходность YTM →</text>
        <text x={padL+8} y={padT+6} className="mk-bm-quad">↑ доходность выше справедливой — компенсирует риск</text>
        {rows.map(b=>{
          const r=bondRisk(b), comp=b.ytm>=bondFair(r);
          return (
            <g key={b.t} className="mk-bm-bub">
              <circle cx={X(r)} cy={Y(b.ytm)} r={9} fill={RELI_COLOR[b.reli]} fillOpacity={comp?0.85:0.28} stroke={RELI_COLOR[b.reli]} strokeWidth={comp?0:1.5}/>
              <text x={X(r)} y={Y(b.ytm)-14} className="mk-bm-lbl" textAnchor="middle">{b.t}</text>
              <title>{b.n} · YTM {window.mkNum(b.ytm,1)}% · {b.agency} · {comp?"компенсирует риск":"тонкая компенсация"}</title>
            </g>
          );
        })}
      </svg>
      <div className="mk-bm-legend">
        <span className="mk-leg"><i style={{background:"var(--pos)"}}/>Надёжные</span>
        <span className="mk-leg"><i style={{background:"var(--amber)"}}/>Средний риск</span>
        <span className="mk-leg"><i style={{background:"var(--neg)"}}/>ВДО</span>
        <span className="mk-leg dim">● над линией — доходность компенсирует риск · ○ под линией — тонкая компенсация</span>
      </div>
    </div>
  );
}

function SegGroup({ label, options, value, onChange }){
  return (
    <div className="mk-seg-group">
      <span className="mk-seg-lbl">{label}</span>
      <div className="mk-seg">
        {options.map(o=>{ const v=Array.isArray(o)?o[0]:o, l=Array.isArray(o)?o[1]:o;
          return <button key={v} className={value===v?"on":""} onClick={()=>onChange(v)}>{l}</button>; })}
      </div>
    </div>
  );
}

function BondsTab({ query }){
  const [coupon,setCoupon]=useStateM("Любой купон");
  const [reli,setReli]=useStateM("Любая надёжность");
  const [sort,setSort]=useStateM("default");
  const [view,setView]=useStateM("rows");
  const reliMap={ "Надёжные":"high","Средний риск":"mid","ВДО":"vdo" };
  let rows=window.MK_BONDS.filter(b=>
    (!query || (b.n+" "+b.t+" "+b.isin).toLowerCase().includes(query.toLowerCase())) &&
    (coupon==="Любой купон" || (coupon==="Фикс"&&b.coupon==="Фикс") || (coupon==="Флоатеры"&&b.coupon==="Флоатер")) &&
    (reli==="Любая надёжность" || b.reli===reliMap[reli])
  );
  if(sort==="ytm") rows=[...rows].sort((a,b)=>b.ytm-a.ytm);
  else if(sort==="spread") rows=[...rows].sort((a,b)=>b.spread-a.spread);
  else if(sort==="dur") rows=[...rows].sort((a,b)=>a.dur-b.dur);
  return (
    <div>
      <div className="mk-filterbar">
        <SegGroup label="Купон" value={coupon} onChange={setCoupon} options={["Любой купон","Фикс","Флоатеры"]} />
        <SegGroup label="Надёжность" value={reli} onChange={setReli} options={["Любая надёжность","Надёжные","Средний риск","ВДО"]} />
        <SegGroup label="Сортировка" value={sort} onChange={setSort} options={[["default","По умолчанию"],["spread","Спред к ОФЗ"],["ytm","Доходность"],["dur","Дюрация"]]} />
        <ViewToggle view={view} setView={setView}/>
      </div>

      <div className="mk-grp-head" style={{marginTop:20}}>Корпоративные<span className="mk-grp-n">{rows.length}</span></div>

      {view==="cards" ? <BondCards rows={rows}/> : (
      <div className="mk-tablewrap">
        <table className="mk-table">
          <thead><tr>
            <th className="l">Выпуск</th>
            <th className="l mk-reli-c">Рынок</th><th className="l mk-reli-c">Агентство</th><th className="l mk-reli-c">Basis</th>
            <th>Спред к ОФЗ</th><th>Доходность (YTM)</th><th>Дюрация</th><th>Цена · погашение</th>
          </tr></thead>
          <tbody>
            {rows.map(b=>(
              <tr key={b.t}>
                <td className="l"><div className="mk-bond-id"><b>{b.t}</b><span className="mk-sub">{b.isin} · {b.n}</span></div></td>
                <td className="l mk-reli-c"><ReliBadge k={b.reli}/></td>
                <td className="l mk-reli-c"><span className="mk-ag">{b.agency}</span></td>
                <td className="l mk-reli-c"><span className="mk-basis">Basis {b.basis}</span></td>
                <td className="num"><span className="mk-spread">+{b.spread}{NB}б.п.</span></td>
                <td className="num strong">{window.mkNum(b.ytm,1)}{NB}%</td>
                <td className="num">{window.mkNum(b.dur,1)}{NB}г</td>
                <td className="num"><div className="mk-pricemat"><b>{window.mkNum(b.price,1)}%</b><span className="mk-sub">{b.mat}</span></div></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length===0 && <div className="mk-empty">Нет выпусков под фильтры.</div>}
      </div>
      )}
    </div>
  );
}

// ===================== FUTURES =====================
function ViewToggle({ view, setView }){
  return (
    <div className="mk-seg-group mk-seg-view">
      <span className="mk-seg-lbl">Вид</span>
      <div className="mk-seg">
        <button className={view==="rows"?"on":""} onClick={()=>setView("rows")}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 4h12M2 8h12M2 12h12" strokeLinecap="round"/></svg>Лента
        </button>
        <button className={view==="cards"?"on":""} onClick={()=>setView("cards")}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>Карточки
        </button>
      </div>
    </div>
  );
}
function BondCards({ rows }){
  if(!rows.length) return <div className="mk-tablewrap"><div className="mk-empty">Нет выпусков под фильтры.</div></div>;
  return <div className="mk-grid">{rows.map(b=>(
    <div key={b.t} className="mk-card mk-card-asset">
      <div className="mk-card-top">
        <span className="mk-mono" style={{background:"color-mix(in srgb,"+RELI_COLOR[b.reli]+" 15%,transparent)", color:RELI_COLOR[b.reli]}}>{b.t.slice(0,2)}</span>
        <div className="mk-card-id"><b>{b.t}</b><span className="mk-card-tk">{b.n}</span></div>
      </div>
      <div className="mk-asset-big"><span className="mk-asset-bigv">{window.mkNum(b.ytm,1)}<span className="mk-cur"> %</span></span><span className="mk-asset-biglbl">YTM</span></div>
      <div className="mk-reli"><ReliBadge k={b.reli}/><span className="mk-ag">{b.agency}</span><span className="mk-basis">Basis {b.basis}</span></div>
      <div className="mk-card-stats">
        <span><i>Спред ОФЗ</i>+{b.spread} б.п.</span>
        <span><i>Дюрация</i>{window.mkNum(b.dur,1)} г</span>
        <span><i>Цена</i>{window.mkNum(b.price,1)}%</span>
      </div>
    </div>
  ))}</div>;
}
function FuturesCards({ items }){
  return <div className="mk-grid">{items.map(f=>(
    <div key={f.t} className="mk-card mk-card-asset">
      <div className="mk-card-top">
        <span className="mk-mono" style={{background:"var(--accent-soft)",color:"var(--accent-2)"}}>{f.t.slice(0,2)}</span>
        <div className="mk-card-id"><b>{f.t}</b><span className="mk-card-tk">{f.n}</span></div>
      </div>
      <div className="mk-asset-big"><LevBadge lev={f.lev}/><span className="mk-asset-biglbl">плечо · риск</span></div>
      <div className="mk-card-stats">
        <span><i>До эксп.</i>{f.exp} дн</span>
        <span><i>ГО</i>{window.mkGrp(f.go)} ₽</span>
        <span><i>Номинал</i>{window.mkGrp(f.nominal)} ₽</span>
        <span><i>Откр. поз.</i>{window.mkGrp(f.oi)}</span>
      </div>
    </div>
  ))}</div>;
}
function FundCards({ items }){
  return <div className="mk-grid">{items.map(f=>(
    <div key={f.t} className="mk-card mk-card-asset">
      <div className="mk-card-top">
        <span className="mk-mono" style={{background:"var(--accent-soft)",color:"var(--accent-2)"}}>{f.t.slice(0,2)}</span>
        <div className="mk-card-id"><b>{f.t}</b><span className="mk-card-tk">{f.n}</span></div>
      </div>
      <div className="mk-asset-big"><span className="mk-asset-bigv">{window.mkNum(f.price,2)}<span className="mk-cur"> ₽</span></span><span className={"mk-delta "+(f.chg>0?"up":f.chg<0?"dn":"fl")}><span className="mk-delta-pct">{f.chg>0?"▲":f.chg<0?"▼":"▬"} {window.mkNum(Math.abs(f.chg),2)}%</span></span></div>
      <div className="mk-card-stats">
        <span className="full"><i>Отслеживает</i>{f.track}</span>
        <span><i>Комиссия</i>{window.mkNum(f.ter,2)}%</span>
        <span><i>СЧА</i>{window.mkNum(f.nav,1)} млрд</span>
      </div>
    </div>
  ))}</div>;
}
function LevBadge({ lev }){
  const tone = lev>=10?"neg":lev>=7?"amber":"warn";
  return <span className={"mk-lev mk-lev-"+tone}>{window.mkNum(lev,1)}×</span>;
}
function FuturesTab({ query }){
  const [grp,setGrp]=useStateM("Все");
  const [view,setView]=useStateM("rows");
  const filt=window.MK_FUTURES.filter(f=>
    (grp==="Все"||f.grp===grp) &&
    (!query||(f.n+" "+f.t).toLowerCase().includes(query.toLowerCase()))
  );
  const groups={}; filt.forEach(f=>{(groups[f.grp]=groups[f.grp]||[]).push(f);});
  const order=window.MK_FUT_GROUPS.filter(g=>groups[g]);
  return (
    <div>
      <div className="mk-callout amber">
        <b>Высокорисковый инструмент.</b> Фьючерс — дериватив со встроенным <b>плечом</b> (усиливает и прибыль, и убыток) и <b>датой экспирации</b>; для хеджа и спекуляции, а не «вложение». Basis показывает анатомию риска — плечо, ГО, срок, — а не торговые сигналы и не «куда пойдёт цена».
      </div>
      <div className="mk-filterbar" style={{marginTop:18}}>
        <SegGroup label="Категория" value={grp} onChange={setGrp} options={["Все",...window.MK_FUT_GROUPS]} />
        <ViewToggle view={view} setView={setView}/>
      </div>
      {order.length===0 && <div className="mk-tablewrap" style={{marginTop:16}}><div className="mk-empty">Ничего не найдено.</div></div>}
      {order.map(g=>(
        <div key={g}>
          <div className="mk-grp-head" style={{marginTop:16}}>{g}<span className="mk-grp-n">{groups[g].length}</span></div>
          {view==="cards" ? <FuturesCards items={groups[g]}/> : (
          <div className="mk-tablewrap">
            <table className="mk-table">
              <thead><tr><th className="l">Контракт</th><th>Плечо</th><th>До экспирации</th><th>ГО</th><th>Номинал</th><th>Откр. позиции</th></tr></thead>
              <tbody>
                {groups[g].map(f=>(
                  <tr key={f.t}>
                    <td className="l"><div className="mk-bond-id"><b>{f.t}</b><span className="mk-sub">{f.n}</span></div></td>
                    <td className="num"><LevBadge lev={f.lev}/></td>
                    <td className="num">{f.exp}{NB}дн</td>
                    <td className="num">{window.mkGrp(f.go)}{NB}₽</td>
                    <td className="num">{window.mkGrp(f.nominal)}{NB}₽</td>
                    <td className="num dim">{window.mkGrp(f.oi)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ===================== FUNDS =====================
function FundsTab({ query }){
  const [grp,setGrp]=useStateM("Все");
  const [view,setView]=useStateM("rows");
  let filt=window.MK_FUNDS.filter(f=>(grp==="Все"||f.grp===grp)&&(!query||(f.n+" "+f.t).toLowerCase().includes(query.toLowerCase())));
  const groups={}; filt.forEach(f=>{(groups[f.grp]=groups[f.grp]||[]).push(f);});
  const order=window.MK_FUND_GROUPS.filter(g=>groups[g]);
  return (
    <div>
      <div className="mk-callout">
        <b>Фонды (БПИФ / ETF)</b> — это корзина активов, а не отдельная идея. Ключевое — <b>что внутри</b>, комиссия фонда (TER) и насколько точно он следует за индексом. Basis показывает состав и издержки, а не «доходность в прошлом как обещание».
      </div>
      <div className="mk-filterbar" style={{marginTop:18}}>
        <SegGroup label="Категория" value={grp} onChange={setGrp} options={["Все",...window.MK_FUND_GROUPS]} />
        <ViewToggle view={view} setView={setView}/>
      </div>
      {order.length===0 && <div className="mk-tablewrap" style={{marginTop:16}}><div className="mk-empty">Ничего не найдено.</div></div>}
      {order.map(g=>(
        <div key={g}>
          <div className="mk-grp-head" style={{marginTop:16}}>{g}<span className="mk-grp-n">{groups[g].length}</span></div>
          {view==="cards" ? <FundCards items={groups[g]}/> : (
          <div className="mk-tablewrap">
            <table className="mk-table">
              <thead><tr><th className="l">Фонд</th><th className="l">Отслеживает</th><th>Цена пая</th><th>За день</th><th>Комиссия (TER)</th><th>СЧА</th></tr></thead>
              <tbody>
                {groups[g].map(f=>(
                  <tr key={f.t}>
                    <td className="l"><div className="mk-bond-id"><b>{f.t}</b><span className="mk-sub">{f.n}</span></div></td>
                    <td className="l dim">{f.track}</td>
                    <td className="num">{window.mkNum(f.price,2)}{NB}₽</td>
                    <td className="num"><span className={"mk-delta "+(f.chg>0?"up":f.chg<0?"dn":"fl")}><span className="mk-delta-pct">{f.chg>0?"▲":f.chg<0?"▼":"▬"} {window.mkNum(Math.abs(f.chg),2)}{NB}%</span></span></td>
                    <td className="num strong">{window.mkNum(f.ter,2)}{NB}%</td>
                    <td className="num dim">{window.mkNum(f.nav,1)}{NB}млрд{NB}₽</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </div>
      ))}
    </div>
  );
}
// ===================== FX & METALS =====================
function PriceList({ rows, dec }){
  return (
    <div className="mk-tablewrap">
      <table className="mk-table">
        <thead><tr><th className="l">Инструмент</th><th>Цена (₽)</th><th>За день</th></tr></thead>
        <tbody>
          {rows.map(r=>(
            <tr key={r.t}>
              <td className="l"><b className="mk-fx-n">{r.n}</b></td>
              <td className="num">{window.mkNum(r.price,dec)}</td>
              <td className="num"><span className={"mk-delta "+(r.chg>0?"up":r.chg<0?"dn":"fl")}><span className="mk-delta-pct">{r.chg>0?"+":""}{window.mkNum(r.chg,2)}{NB}%</span></span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function FxMetalsTab(){
  return (
    <div>
      <div className="mk-callout">
        Валюта и металлы — это <b>не «актив со справедливой ценой»</b>, а макро-индикаторы. Курс рубля зависит от ставки ЦБ, нефти и платёжного баланса; золото — защитный актив, остальные металлы циклически-промышленные. Basis объясняет, что закладывает рынок и какова роль в портфеле, а не «куда пойдёт цена». После санкций 2024 на бирже ликвидны только <b>доллар и юань</b>.
      </div>
      <div className="mk-grp-head" style={{marginTop:18}}>Валюты<span className="mk-grp-n">{window.MK_FX.length}</span></div>
      <PriceList rows={window.MK_FX} dec={3}/>
      <div className="mk-grp-head" style={{marginTop:20}}>Драгметаллы<span className="mk-grp-n">{window.MK_METALS.length}</span></div>
      <PriceList rows={window.MK_METALS} dec={2}/>
    </div>
  );
}

// ===================== OPTIONS =====================
function OptionsTab(){
  return (
    <div>
      <div className="mk-callout amber">
        <b>Опционы — инструмент для опытных.</b> Это право (не обязанность) купить или продать базовый актив по цене страйк до экспирации. Цена зависит не только от направления, но и от <b>времени</b> и <b>волатильности</b> — можно быть «правым по рынку» и всё равно потерять. Basis раскрывает структуру риска, а не сигналы.
      </div>
      <div className="mk-options-empty">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17l5-5 4 3 6-7"/><path d="M16 8h4v4"/></svg>
        <div className="mk-opt-t">Анализ опционов скоро</div>
        <p>Готовим разбор по базовым активам: цепочки страйков, подразумеваемую волатильность и анатомию риска позиции — в логике Basis, без торговых сигналов.</p>
        <button className="mk-btn-ghost">Уведомить о запуске</button>
      </div>
    </div>
  );
}

Object.assign(window, { MKStocksTab:StocksTab, MKBondsTab:BondsTab, MKFuturesTab:FuturesTab, MKFundsTab:FundsTab, MKFxMetalsTab:FxMetalsTab, MKOptionsTab:OptionsTab });
