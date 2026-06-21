// Basis Screener — criteria rail: HistogramRangeSlider, criterion rows, group sections. Exported to window.
const { useState: useStateRail, useRef, useCallback } = React;

// Dual-handle range slider with the universe distribution histogram behind it.
function HistogramRangeSlider({ mkey, range, onChange }){
  const M = window.SC_METRICS[mkey];
  const [a,b] = M.dom;
  const [lo,hi] = range || M.dom;
  const trackRef = useRef(null);
  const hist = window.scHistogram(mkey);
  const hmax = Math.max(...hist, 1);
  const drag = useRef(null);

  const pct = (v)=> ((v-a)/(b-a))*100;
  const snap = (v)=>{ const s=M.step; return Math.round(v/s)*s; };
  const fromX = useCallback((clientX)=>{
    const el=trackRef.current; if(!el) return lo;
    const r=el.getBoundingClientRect();
    let t=(clientX-r.left)/r.width; t=Math.max(0,Math.min(1,t));
    return snap(a + t*(b-a));
  },[a,b,lo]);

  const onDown = (which)=>(e)=>{
    e.preventDefault(); drag.current=which;
    const move=(ev)=>{
      const cx = ev.touches? ev.touches[0].clientX : ev.clientX;
      let v=fromX(cx);
      onChange(which==="lo" ? [Math.min(v,hi), hi] : [lo, Math.max(v,lo)]);
    };
    const up=()=>{ drag.current=null; window.removeEventListener("pointermove",move); window.removeEventListener("pointerup",up); };
    window.addEventListener("pointermove",move); window.addEventListener("pointerup",up);
  };

  // bucket center value → inside selected range?
  const bw = (b-a)/hist.length;
  return (
    <div className="sc-hrs">
      <div className="sc-hrs-hist" aria-hidden="true">
        {hist.map((c,i)=>{
          const center=a+(i+0.5)*bw;
          const inside = center>=lo && center<=hi;
          return <span key={i} className={"sc-bar"+(inside?" on":"")} style={{height:(c/hmax*100)+"%"}} />;
        })}
      </div>
      <div className="sc-hrs-track" ref={trackRef}>
        <span className="sc-hrs-fill" style={{left:pct(lo)+"%", right:(100-pct(hi))+"%"}} />
        <button className="sc-hrs-thumb" style={{left:pct(lo)+"%"}} onPointerDown={onDown("lo")} aria-label="Минимум" />
        <button className="sc-hrs-thumb" style={{left:pct(hi)+"%"}} onPointerDown={onDown("hi")} aria-label="Максимум" />
      </div>
    </div>
  );
}

function fmtBound(mkey, v){
  const M=window.SC_METRICS[mkey];
  if(M.money) return window.scMoney(v);
  return window.scNum(v, M.dec) + (M.unit||"");
}

// A single active criterion: label, live match count, range readout, slider.
function CriterionRow({ mkey, range, onChange, onRemove, matchCount }){
  const M=window.SC_METRICS[mkey];
  const [lo,hi]=range;
  const atFloor = lo<=M.dom[0]+1e-9, atCeil = hi>=M.dom[1]-1e-9;
  let readout;
  if(atFloor && !atCeil) readout = "≤ "+fmtBound(mkey,hi);
  else if(!atFloor && atCeil) readout = "≥ "+fmtBound(mkey,lo);
  else readout = fmtBound(mkey,lo)+" – "+fmtBound(mkey,hi);
  return (
    <div className="sc-crit">
      <div className="sc-crit-head">
        <span className="sc-crit-label">{M.label}</span>
        <span className="sc-crit-count">{matchCount}</span>
        <button className="sc-crit-x" onClick={onRemove} aria-label="Убрать критерий">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>
        </button>
      </div>
      <div className="sc-crit-readout">{readout}</div>
      <HistogramRangeSlider mkey={mkey} range={range} onChange={onChange} />
    </div>
  );
}

// Add-criterion menu grouped by category.
function AddCriterion({ activeKeys, onAdd }){
  const [open,setOpen]=useStateRail(false);
  const avail = Object.keys(window.SC_METRICS).filter(k=>!activeKeys.includes(k));
  return (
    <div className="sc-add">
      <button className="sc-add-btn" onClick={()=>setOpen(o=>!o)} aria-expanded={open}>
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M8 3v10M3 8h10"/></svg>
        Добавить критерий
      </button>
      {open && (
        <div className="sc-add-menu" onMouseLeave={()=>setOpen(false)}>
          {window.SC_METRIC_GROUPS.map(g=>{
            const ks=avail.filter(k=>window.SC_METRICS[k].group===g);
            if(!ks.length) return null;
            return (
              <div key={g} className="sc-add-grp">
                <div className="sc-add-grp-t">{g}</div>
                {ks.map(k=>(
                  <button key={k} className="sc-add-item" onClick={()=>{ onAdd(k); setOpen(false); }}>
                    {window.SC_METRICS[k].label}
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Sector multi-select as chips.
function SectorFilter({ selected, onToggle }){
  return (
    <div className="sc-sectors">
      {window.SC_SECTORS.map(s=>(
        <button key={s} className={"sc-sec-chip"+(selected.includes(s)?" on":"")} onClick={()=>onToggle(s)}>
          <span className="sc-sec-dot" style={{background:window.SC_SECTOR_COLORS[s]}} />{s}
        </button>
      ))}
    </div>
  );
}

// Full rail.
function CriteriaRail({ ranges, sectors, onRangeChange, onAdd, onRemove, onToggleSector, onReset, resultCount, onCollapse }){
  const activeKeys = Object.keys(ranges);
  const total = window.SC_UNIVERSE.length;
  return (
    <aside className="sc-rail">
      <div className="sc-rail-head">
        <div>
          <div className="sc-eyebrow">Критерии скрина</div>
          <div className="sc-rail-title">Конструктор фильтра</div>
        </div>
        <div className="sc-rail-head-act">
          <button className="sc-reset" onClick={onReset}>Сбросить</button>
          {onCollapse && (
            <button className="sc-collapse" onClick={onCollapse} title="Свернуть фильтры" aria-label="Свернуть панель фильтров">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 3.5L5 8l4.5 4.5"/><path d="M13 3.5v9"/></svg>
            </button>
          )}
        </div>
      </div>

      <div className="sc-funnel">
        <div className="sc-funnel-bar">
          <span className="sc-funnel-fill" style={{width:(resultCount/total*100)+"%"}} />
        </div>
        <div className="sc-funnel-txt">
          <b>{resultCount}</b> из {total} бумаг проходят
          <span className="sc-funnel-sub">{activeKeys.length+(sectors.length?1:0)} активных условий</span>
        </div>
      </div>

      <div className="sc-rail-scroll">
        <SectorFilter selected={sectors} onToggle={onToggleSector} />
        {activeKeys.length===0 && sectors.length===0 && (
          <div className="sc-empty">Фильтров нет — показаны все бумаги. Добавьте критерий или выберите готовый скрин.</div>
        )}
        {window.SC_METRIC_GROUPS.map(g=>{
          const ks=activeKeys.filter(k=>window.SC_METRICS[k].group===g);
          if(!ks.length) return null;
          return (
            <div key={g} className="sc-crit-grp">
              <div className="sc-crit-grp-t">{g}</div>
              {ks.map(k=>(
                <CriterionRow key={k} mkey={k} range={ranges[k]}
                  matchCount={window.scApply({[k]:ranges[k]}, sectors).length}
                  onChange={(r)=>onRangeChange(k,r)} onRemove={()=>onRemove(k)} />
              ))}
            </div>
          );
        })}
        <AddCriterion activeKeys={activeKeys} onAdd={onAdd} />
      </div>
    </aside>
  );
}

Object.assign(window, { SCCriteriaRail:CriteriaRail });
