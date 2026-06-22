// Basis Screener — results: toolbar, table (percentile cells), map scatter, detail drawer. Exported to window.
const { useState: useStateR } = React;

function ConfDots({ level }){
  const n = level==="high"?3 : level==="medium"?2 : 1;
  return (
    <span className="sc-conf" title={"Уверенность: "+(level==="high"?"высокая":level==="medium"?"средняя":"низкая")}>
      {[0,1,2].map(i=> <i key={i} className={i<n?"on":""} />)}
    </span>
  );
}

// A metric cell: mono value + thin percentile bar (good-direction fill).
function MetricCell({ mkey, v }){
  if(v==null) return <td className="sc-td sc-num sc-na">—</td>;
  const M=window.SC_METRICS[mkey];
  const pos=window.scDomPos(mkey,v);          // geometry along domain
  const good=window.scGoodPct(mkey,v);        // 0..1 quality
  const txt = (M.money? window.scMoney(v) : window.scNum(v,M.dec)+(M.unit||""));
  const strong = good>=0.8;
  return (
    <td className="sc-td sc-num">
      <span className="sc-cellval">{txt}</span>
      <span className="sc-cellbar"><i className={strong?"strong":""} style={{width:Math.max(4,pos*100)+"%"}} /></span>
    </td>
  );
}

function ScoreBadge({ s }){
  return <span className="sc-score" style={{background:window.scScoreColor(s)}}>{s}</span>;
}

// Continuous green→orange→red legend strip for the Basis score.
function ScoreScale({ compact }){
  const stops=[];
  for(let i=0;i<=10;i++){ const s=45+(i/10)*(82-45); stops.push(window.scScoreColor(s)); }
  return (
    <span className={"sc-scale"+(compact?" compact":"")} title="Basis-балл: качество фундаментала по совокупности показателей">
      <span className="sc-scale-bar" style={{background:`linear-gradient(90deg, ${stops.join(",")})`}} />
      <span className="sc-scale-lbl"><b>Basis-балл</b> — слабее → сильнее</span>
    </span>
  );
}

function SortHead({ label, k, sort, setSort, align="right", title }){
  const active=sort.key===k;
  return (
    <th className={"sc-th"+(align==="left"?" sc-th-l":"")+(active?" on":"")} title={title}
        onClick={()=>setSort(s=> ({ key:k, dir: s.key===k && s.dir==="desc" ? "asc":"desc" }))}>
      <span>{label}</span>
      <svg className="sc-sort" width="9" height="11" viewBox="0 0 9 11" aria-hidden="true">
        <path d="M4.5 0l3 4h-6z" className={active&&sort.dir==="asc"?"a":""} />
        <path d="M4.5 11l-3-4h6z" className={active&&sort.dir==="desc"?"a":""} />
      </svg>
    </th>
  );
}

function ResultsTable({ rows, sort, setSort, density, onPick, picked }){
  return (
    <div className={"sc-tablewrap sc-d-"+density}>
      <table className="sc-table">
        <thead>
          <tr>
            <SortHead label="Компания" k="n" sort={sort} setSort={setSort} align="left" />
            <SortHead label="Basis" k="score" sort={sort} setSort={setSort} title="Композитная оценка Basis" />
            {window.SC_TABLE_METRICS.map(k=>(
              <SortHead key={k} label={window.SC_METRICS[k].label} k={k} sort={sort} setSort={setSort} />
            ))}
            <th className="sc-th sc-th-r2">Изм.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r=>(
            <tr key={r.t} className={picked&&picked.t===r.t?"on":""} onClick={()=>onPick(r)}>
              <td className="sc-td sc-id">
                <span className="sc-mono" style={{background:window.SC_SECTOR_COLORS[r.sec]+"22", color:window.SC_SECTOR_COLORS[r.sec]}}>{r.t.slice(0,2)}</span>
                <span className="sc-idtext">
                  <b>{r.n}</b>
                  <span className="sc-idsub">{r.t} · {r.sec}</span>
                </span>
              </td>
              <td className="sc-td sc-num"><span className="sc-scorewrap"><ScoreBadge s={r.score} /><ConfDots level={r.conf} /></span></td>
              {window.SC_TABLE_METRICS.map(k=> <MetricCell key={k} mkey={k} v={r[k]} />)}
              <td className="sc-td sc-num">
                <span className={"sc-delta "+(r.chg>0?"up":r.chg<0?"dn":"fl")}>
                  {r.chg>0?"▲":r.chg<0?"▼":"▬"} {window.scNum(Math.abs(r.chg),1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length===0 && <div className="sc-noresult">Ни одна бумага не проходит все условия. Ослабьте критерии слева.</div>}
    </div>
  );
}

// Custom axis dropdown — styled like the sector picker (popover, grouped, no native select).
function AxisSelect({ side, value, onChange }){
  const [open,setOpen]=useStateR(false);
  const cur=window.scAxisDef(value);
  const groups=[{t:"Оценка Basis",keys:["score"]}];
  window.SC_METRIC_GROUPS.forEach(g=> groups.push({ t:g, keys:Object.keys(window.SC_METRICS).filter(k=>window.SC_METRICS[k].group===g) }));
  return (
    <div className="sc-axdd-wrap">
      <span className="sc-axdd-side">Ось {side}</span>
      <button className={"sc-axdd"+(open?" open":"")} onClick={()=>setOpen(o=>!o)} aria-expanded={open}>
        <span className="sc-axdd-cur">{cur.label}{cur.unit?<span className="sc-axdd-unit">{cur.unit}</span>:null}</span>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" style={{transform:open?"rotate(180deg)":"none",transition:"transform .15s"}}><path d="M4 6l4 4 4-4"/></svg>
      </button>
      {open && (
        <div className="sc-axdd-menu" onMouseLeave={()=>setOpen(false)}>
          {groups.map((grp,gi)=>(
            <div key={grp.t} className="sc-axdd-grp">
              <div className="sc-axdd-grp-t">{grp.t}</div>
              {grp.keys.map(k=>{
                const d=window.scAxisDef(k);
                return (
                  <button key={k} className={"sc-axdd-item"+(k===value?" on":"")} onClick={()=>{ onChange(k); setOpen(false); }}>
                    <span>{d.label}</span>
                    {d.unit && <span className="sc-axdd-item-u">{d.unit}</span>}
                    {k===value && <svg className="sc-axdd-chk" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8.5l3.5 3.5L13 4.5"/></svg>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Map view: any metric (or Basis score) on each axis · bubble = mcap · color = sector.
function MapView({ rows, onPick, picked }){
  const [xKey,setXKey]=useStateR("pe");
  const [yKey,setYKey]=useStateR("score");
  const xa=window.scAxisDef(xKey), ya=window.scAxisDef(yKey);
  const W=760, H=452, padL=60, padR=26, padT=30, padB=64;
  const span=(a)=> (a.dom[1]-a.dom[0])||1;
  const X=(v)=> padL + (Math.max(xa.dom[0],Math.min(xa.dom[1],v))-xa.dom[0])/span(xa)*(W-padL-padR);
  const Y=(v)=> H-padB - (Math.max(ya.dom[0],Math.min(ya.dom[1],v))-ya.dom[0])/span(ya)*(H-padT-padB);
  const R=(m)=> 7+Math.sqrt(m)/14;
  const xMid=(xa.dom[0]+xa.dom[1])/2, yMid=(ya.dom[0]+ya.dom[1])/2;
  const fmtAx=(a,v)=> a.money? window.scMoney(v) : window.scNum(v, a.key==="score"?0:(window.SC_METRICS[a.key]?window.SC_METRICS[a.key].dec:0))+(a.unit||"");
  // axis direction hints
  const xHint = xa.dir==="low" ? "← лучше" : "лучше →";
  const yHint = ya.dir==="low" ? "↓ лучше" : "↑ лучше";
  const valid = rows.filter(r=> xa.get(r)!=null && ya.get(r)!=null);
  return (
    <div className="sc-map">
      <div className="sc-map-ctrls">
        <AxisSelect side="X" value={xKey} onChange={setXKey} />
        <button className="sc-axswap" onClick={()=>{ setXKey(yKey); setYKey(xKey); }} title="Поменять оси местами" aria-label="Поменять оси">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3L3 5l2 2M3 5h7M11 13l2-2-2-2M13 11H6"/></svg>
        </button>
        <AxisSelect side="Y" value={yKey} onChange={setYKey} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sc-map-svg" preserveAspectRatio="xMidYMid meet">
        {/* median crosshair */}
        <line x1={X(xMid)} y1={padT} x2={X(xMid)} y2={H-padB} className="sc-map-guide" />
        <line x1={padL} y1={Y(yMid)} x2={W-padR} y2={Y(yMid)} className="sc-map-guide" />
        {/* axis ticks */}
        {[0,0.5,1].map((f,i)=>{ const v=xa.dom[0]+f*span(xa); return <text key={"x"+i} x={X(v)} y={H-padB+18} className="sc-map-tick" textAnchor="middle">{fmtAx(xa,v)}</text>; })}
        {[0,0.5,1].map((f,i)=>{ const v=ya.dom[0]+f*span(ya); return <text key={"y"+i} x={padL-9} y={Y(v)+3} className="sc-map-tick" textAnchor="end">{fmtAx(ya,v)}</text>; })}
        {/* axis titles */}
        <text x={(padL+W-padR)/2} y={H-8} className="sc-map-axis" textAnchor="middle">{xa.label} · {xHint}</text>
        <text x={18} y={(padT+H-padB)/2} className="sc-map-axis" textAnchor="middle" transform={`rotate(-90 18 ${(padT+H-padB)/2})`}>{ya.label} · {yHint}</text>
        {/* bubbles */}
        {valid.map(r=>{
          const on = picked && picked.t===r.t;
          return (
            <g key={r.t} className={"sc-bub"+(on?" on":"")} onClick={()=>onPick(r)} style={{cursor:"pointer"}}>
              <circle cx={X(xa.get(r))} cy={Y(ya.get(r))} r={R(r.mcap)} fill={window.SC_SECTOR_COLORS[r.sec]} fillOpacity={on?0.85:0.5} stroke={window.SC_SECTOR_COLORS[r.sec]} strokeWidth={on?2:1} />
              <text x={X(xa.get(r))} y={Y(ya.get(r))+3} className="sc-bub-t" textAnchor="middle">{r.t}</text>
            </g>
          );
        })}
      </svg>
      <div className="sc-map-legend">
        {window.SC_SECTORS.map(s=> <span key={s} className="sc-leg"><i style={{background:window.SC_SECTOR_COLORS[s]}} />{s}</span>)}
        <span className="sc-leg sc-leg-size"><i className="sz sz1"/><i className="sz sz2"/><i className="sz sz3"/>размер = капитализация</span>
        {valid.length<rows.length && <span className="sc-leg sc-leg-na">{rows.length-valid.length} без данных по осям скрыты</span>}
      </div>
    </div>
  );
}

// Right slide-over detail.
function DetailDrawer({ row, onClose }){
  if(!row) return null;
  const stats=[["pe","ev","pb"],["roe","mgn","nd"],["div","fcf","rev"]];
  return (
    <>
      <div className="sc-scrim" onClick={onClose} />
      <aside className="sc-drawer" role="dialog" aria-label={"Детали "+row.n}>
        <div className="sc-dr-head">
          <span className="sc-mono lg" style={{background:window.SC_SECTOR_COLORS[row.sec]+"22", color:window.SC_SECTOR_COLORS[row.sec]}}>{row.t.slice(0,2)}</span>
          <div className="sc-dr-id">
            <div className="sc-dr-name">{row.n}</div>
            <div className="sc-dr-sub">{row.t} · {row.sec}</div>
          </div>
          <button className="sc-dr-x" onClick={onClose} aria-label="Закрыть">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>
          </button>
        </div>
        <div className="sc-dr-price">
          <span className="sc-dr-px">{window.scNum(row.price,2)} ₽</span>
          <span className={"sc-delta "+(row.chg>0?"up":row.chg<0?"dn":"fl")}>{row.chg>0?"▲":row.chg<0?"▼":"▬"} {window.scNum(Math.abs(row.chg),1)}%</span>
          <span className="sc-dr-score"><ScoreBadge s={row.score} /><ConfDots level={row.conf} /></span>
        </div>
        <div className="sc-dr-thesis">{window.SC_THESIS[row.t]}</div>
        <div className="sc-eyebrow" style={{margin:"4px 0 8px"}}>Показатели · позиция на рынке</div>
        <div className="sc-dr-stats">
          {stats.flat().map(k=>{
            const M=window.SC_METRICS[k], v=row[k];
            const good=v==null?null:window.scGoodPct(k,v);
            return (
              <div key={k} className="sc-dr-stat">
                <div className="sc-dr-stat-l">{M.label}</div>
                <div className="sc-dr-stat-v">{v==null?"—":(M.money?window.scMoney(v):window.scNum(v,M.dec)+(M.unit||""))}</div>
                <div className="sc-dr-stat-bar"><i style={{width:(good==null?0:Math.max(4,good*100))+"%"}} className={good!=null&&good>=0.8?"strong":""} /></div>
              </div>
            );
          })}
        </div>
        <div className="sc-dr-actions">
          <a className="sc-btn-primary" href="../Company Card.html">Открыть карточку компании</a>
          <button className="sc-btn-ghost">В наблюдение</button>
        </div>
        <p className="sc-dr-note">Композитная оценка и позиции — аналитический ориентир Basis, не инвестиционная рекомендация.</p>
      </aside>
    </>
  );
}

Object.assign(window, { SCResultsTable:ResultsTable, SCMapView:MapView, SCDetailDrawer:DetailDrawer, SCScoreScale:ScoreScale });
