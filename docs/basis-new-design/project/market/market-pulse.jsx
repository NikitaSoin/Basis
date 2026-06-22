// Basis Market — situational-awareness layer: MarketPulse, SectorHeatmap, Movers. Exported to window.
const { useState: useStatePulse } = React;
const NBP="\u00A0";

// daily-change → diverging heat color (red↔neutral↔green), works on both themes
function heatColor(chg){
  const x=Math.max(-3,Math.min(3,chg))/3; // -1..1
  if(Math.abs(x)<0.05) return "hsl(42 6% 62%)";
  if(x>0){ const k=x; return `hsl(148 ${(34+44*k).toFixed(0)}% ${(45-7*k).toFixed(0)}%)`; }
  const k=-x; return `hsl(352 ${(36+42*k).toFixed(0)}% ${(53-7*k).toFixed(0)}%)`;
}

function Spark({ data, w=132, h=38, color="var(--accent)" }){
  const min=Math.min(...data), max=Math.max(...data), rng=(max-min)||1;
  const pts=data.map((v,i)=>[ (i/(data.length-1))*w, h-4-((v-min)/rng)*(h-8) ]);
  const d=pts.map((p,i)=>(i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join(" ");
  const area=d+` L${w} ${h} L0 ${h} Z`;
  const id="sp"+Math.round(data[0]);
  return (
    <svg width={w} height={h} className="mk-spark" aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".22"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <path d={area} fill={`url(#${id})`}/>
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round"/>
    </svg>
  );
}

function DirArrow({ dir }){
  if(dir>0) return <span className="mk-d up">▲</span>;
  if(dir<0) return <span className="mk-d dn">▼</span>;
  return <span className="mk-d fl">▬</span>;
}

function MarketPulse(){
  const I=window.MK_INDEX, D=window.MK_DRIVERS, T=window.MK_MARKET_TONE;
  const S=window.MK_STOCKS;
  const adv=S.filter(s=>s.chg>0).length, dec=S.filter(s=>s.chg<0).length, flat=S.length-adv-dec;
  const total=S.length;
  const tc=window.mkToneColor(T.tone);
  return (
    <div className="mk-pulse">
      <div className="mk-pulse-idx">
        <div className="mk-eyebrow">{I.name}</div>
        <div className="mk-idx-row">
          <span className="mk-idx-level">{window.mkNum(I.level,1)}</span>
          <span className={"mk-delta "+(I.chg>0?"up":I.chg<0?"dn":"fl")}><span className="mk-delta-pct">{I.chg>0?"▲":"▼"} {window.mkNum(Math.abs(I.chg),2)}{NBP}%</span></span>
        </div>
        <Spark data={I.spark} color={I.chg>=0?"var(--pos)":"var(--neg)"}/>
      </div>

      <div className="mk-pulse-breadth">
        <div className="mk-eyebrow">Ширина рынка</div>
        <div className="mk-breadth-bar">
          <span className="seg up" style={{flexGrow:adv}} />
          <span className="seg fl" style={{flexGrow:flat||0.2}} />
          <span className="seg dn" style={{flexGrow:dec}} />
        </div>
        <div className="mk-breadth-legend">
          <span className="up"><b>{adv}</b> растут</span>
          <span className="fl"><b>{flat}</b> без изм.</span>
          <span className="dn"><b>{dec}</b> падают</span>
        </div>
        <div className="mk-tone-row">
          <span className="mk-tone-dot" style={{background:tc}}/>
          <span>Тон рынка: <b style={{color:tc}}>{T.label}</b></span>
        </div>
      </div>

      <div className="mk-pulse-drivers">
        <div className="mk-eyebrow">Что движет рынком сегодня</div>
        <div className="mk-drivers">
          {D.map(d=>(
            <div key={d.name} className="mk-driver">
              <div className="mk-driver-n">{d.name}</div>
              <div className="mk-driver-v">{d.val} <DirArrow dir={d.dir}/></div>
              <div className="mk-driver-e">{d.effect}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Treemap-style sector heatmap. Tiles sized by mcap, colored by daily change.
function SectorHeatmap({ sector, onOpen }){
  let rows=window.MK_STOCKS;
  if(sector && sector!=="Все") rows=rows.filter(s=>s.sec===sector);
  const groups={}; rows.forEach(s=>{(groups[s.sec]=groups[s.sec]||[]).push(s);});
  const order=window.MK_STOCK_SECTORS.filter(g=>groups[g]);
  return (
    <div className="mk-heat">
      <div className="mk-heat-head">
        <span className="mk-heat-title">Карта рынка</span>
        <div className="mk-heat-legend">
          <span>Падение</span>
          <span className="mk-heat-scale" />
          <span>Рост</span>
        </div>
      </div>
      {order.map(g=>{
        const items=[...groups[g]].sort((a,b)=>b.mcap-a.mcap);
        const avg=items.reduce((s,x)=>s+x.chg,0)/items.length;
        const cap=items.reduce((s,x)=>s+x.mcap,0);
        return (
          <div key={g} className="mk-heat-band">
            <div className="mk-heat-band-h">
              <span className="mk-heat-band-dot" style={{background:window.MK_SECTOR_COLORS[g]}}/>
              <span className="mk-heat-band-n">{g}</span>
              <span className={"mk-heat-band-avg "+(avg>0?"up":avg<0?"dn":"fl")}>{avg>0?"+":""}{window.mkNum(avg,2)}{NBP}%</span>
              <span className="mk-heat-band-cap">{window.mkMoney(cap)}</span>
            </div>
            <div className="mk-heat-tiles">
              {items.map(s=>{
                const big=s.mcap>=1400;
                return (
                  <button key={s.t} className={"mk-tile"+(big?" big":"")} onClick={()=>onOpen(s)}
                    style={{flexGrow:s.mcap, flexBasis:Math.max(54,s.mcap/22)+"px", background:heatColor(s.chg)}}
                    title={`${s.n} · ${s.chg>0?"+":""}${window.mkNum(s.chg,2)}%`}>
                    <span className="mk-tile-t">{s.t}</span>
                    <span className="mk-tile-c">{s.chg>0?"+":""}{window.mkNum(s.chg,1)}%</span>
                    {big && <span className="mk-tile-n">{s.n}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MoverRow({ s, onOpen }){
  return (
    <button className="mk-mv" onClick={()=>onOpen(s)}>
      <span className="mk-mono sm" style={{background:(window.MK_SECTOR_COLORS[s.sec]||"var(--accent)")+"22", color:window.MK_SECTOR_COLORS[s.sec]||"var(--accent)"}}>{s.t.slice(0,2)}</span>
      <span className="mk-mv-id"><b>{s.n}</b><span className="mk-mv-tk">{s.t}</span></span>
      <span className="mk-mv-px">{window.mkNum(s.price,2)}<span className="mk-cur"> ₽</span></span>
      <span className={"mk-mv-chg "+(s.chg>0?"up":s.chg<0?"dn":"fl")}>{s.chg>0?"▲":s.chg<0?"▼":"▬"} {window.mkNum(Math.abs(s.chg),2)}%</span>
    </button>
  );
}
function Movers({ onOpen }){
  const sorted=[...window.MK_STOCKS].sort((a,b)=>b.chg-a.chg);
  const gain=sorted.slice(0,5), lose=[...sorted].reverse().slice(0,5);
  return (
    <div className="mk-movers">
      <div className="mk-mv-col">
        <div className="mk-eyebrow up-e">↑ Лидеры роста</div>
        {gain.map(s=><MoverRow key={s.t} s={s} onOpen={onOpen}/>)}
      </div>
      <div className="mk-mv-col">
        <div className="mk-eyebrow dn-e">↓ Лидеры падения</div>
        {lose.map(s=><MoverRow key={s.t} s={s} onOpen={onOpen}/>)}
      </div>
    </div>
  );
}

Object.assign(window, { MKMarketPulse:MarketPulse, MKSectorHeatmap:SectorHeatmap, MKMovers:Movers, MKSectorNav:SectorNav, MKStockRows:StockRows });

// ===== Sector navigator — each chip carries its day performance =====
function SectorNav({ sector, onSelect }){
  const S=window.MK_STOCKS;
  const stats=window.MK_STOCK_SECTORS.map(g=>{
    const items=S.filter(x=>x.sec===g);
    if(!items.length) return null;
    return { g, n:items.length, avg:items.reduce((s,x)=>s+x.chg,0)/items.length };
  }).filter(Boolean);
  const allAvg=S.reduce((s,x)=>s+x.chg,0)/S.length;
  return (
    <div className="mk-secnav">
      <button className={"mk-secn all"+(sector==="Все"?" on":"")} onClick={()=>onSelect("Все")}>
        <span className="mk-secn-top"><span className="mk-secn-alldot"/>Все секторы</span>
        <span className="mk-secn-bot"><span className="mk-secn-n">{S.length} бумаг</span><span className={"mk-secn-chg "+(allAvg>0?"up":allAvg<0?"dn":"fl")}>{allAvg>0?"+":""}{window.mkNum(allAvg,2)}%</span></span>
      </button>
      {stats.map(s=>(
        <button key={s.g} className={"mk-secn"+(sector===s.g?" on":"")} onClick={()=>onSelect(s.g)} style={{"--sc":window.MK_SECTOR_COLORS[s.g]}}>
          <span className="mk-secn-top"><span className="mk-secn-dot" style={{background:window.MK_SECTOR_COLORS[s.g]}}/>{s.g}</span>
          <span className="mk-secn-bot"><span className="mk-secn-n">{s.n} бум.</span><span className={"mk-secn-chg "+(s.avg>0?"up":s.avg<0?"dn":"fl")}>{s.avg>0?"+":""}{window.mkNum(s.avg,2)}%</span></span>
        </button>
      ))}
    </div>
  );
}

// ===== Dense "Лента" row view =====
function toneLabel(t){ return t>=72?"Конструктивно":t>=58?"Нейтрально":"Осторожно"; }
function StockRows({ query, sector, onOpen }){
  const rows=window.MK_STOCKS.filter(s=>(sector==="Все"||s.sec===sector)&&(!query||(s.n+" "+s.t).toLowerCase().includes(query.toLowerCase())));
  if(!rows.length) return <div className="mk-empty">Ничего не найдено. Измените запрос или сектор.</div>;
  return (
    <div className="mk-tablewrap" style={{marginTop:18}}>
      <table className="mk-table mk-rows">
        <thead><tr><th className="l">Бумага</th><th>Цена</th><th>За день</th><th>Капитализация</th><th className="l">К справедливой цене</th></tr></thead>
        <tbody>
          {rows.map(s=>{
            const fv=Math.round((s.tone-58)*0.85), tc=window.mkFvColor(fv), n=s.conf==="high"?3:s.conf==="medium"?2:1;
            return (
              <tr key={s.t} onClick={()=>onOpen(s)} style={{cursor:"pointer"}}>
                <td className="l">
                  <div className="mk-row-id">
                    <span className="mk-tonebar" style={{background:tc}} title="Тон Basis"/>
                    <span className="mk-mono sm" style={{background:(window.MK_SECTOR_COLORS[s.sec]||"var(--accent)")+"22", color:window.MK_SECTOR_COLORS[s.sec]||"var(--accent)"}}>{s.t.slice(0,2)}</span>
                    <span className="mk-bond-id"><b>{s.n}</b><span className="mk-sub">{s.t} · {s.sec}</span></span>
                  </div>
                </td>
                <td className="num">{window.mkNum(s.price,2)}{NBP}₽</td>
                <td className="num"><span className={"mk-delta "+(s.chg>0?"up":s.chg<0?"dn":"fl")}><span className="mk-delta-pct">{s.chg>0?"▲":s.chg<0?"▼":"▬"} {window.mkNum(Math.abs(s.chg),2)}%</span></span></td>
                <td className="num dim">{window.mkMoney(s.mcap)}</td>
                <td className="l"><span className="mk-row-tone"><span className="mk-tone-dot" style={{background:tc}}/><span style={{color:tc,fontWeight:600,fontSize:13,fontFamily:"'JetBrains Mono',monospace"}}>{fv>0?"+":""}{fv}%</span><span className="mk-conf">{[0,1,2].map(i=><i key={i} className={i<n?"on":""}/>)}</span></span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
