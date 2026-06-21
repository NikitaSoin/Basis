// Basis Screener — universe data, criteria, presets, helpers. Exported to window.
// Illustrative mock data for ~20 liquid MOEX names. Numbers are not real quotes.

const NB = "\u00A0", NN = "\u202F";

// fmt helpers (ru-RU): comma decimal, narrow-nbsp grouping
function grp(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NN); }
function num(v, d=1){ if(v==null) return null; const s=v.toFixed(d).replace(".",","); const [i,f]=s.split(","); return grp(i)+(f?","+f:""); }
function money(v){ // млрд ₽
  if(v==null) return null;
  if(v>=1000) return num(v/1000,2)+NB+"трлн";
  return grp(Math.round(v))+NB+"млрд";
}

// Universe: 20 names. Financials (SBER, MOEX) have N/A on EV/EBITDA, margin, ND — kept honest.
const UNIVERSE = [
  { t:"TATN", n:"Татнефть",   sec:"Нефтегаз",  price:648,   chg:0.4,  mcap:1505, pe:5.2, ev:3.0, pb:1.3, roe:23, mgn:28, nd:-0.1, rev:5,  div:13.1, fcf:12, score:80, conf:"high"   },
  { t:"LKOH", n:"Лукойл",     sec:"Нефтегаз",  price:7412,  chg:0.3,  mcap:5134, pe:4.4, ev:2.6, pb:0.78,roe:19, mgn:21, nd:-0.2, rev:3,  div:12.6, fcf:14, score:81, conf:"high"   },
  { t:"NVTK", n:"Новатэк",    sec:"Нефтегаз",  price:1142,  chg:0.6,  mcap:3468, pe:6.4, ev:5.0, pb:1.4, roe:24, mgn:60, nd:0.3,  rev:9,  div:7.4,  fcf:6,  score:79, conf:"high"   },
  { t:"SBER", n:"Сбербанк",   sec:"Финансы",   price:317.82,chg:1.4,  mcap:6845, pe:4.1, ev:null,pb:0.92,roe:24, mgn:null,nd:null, rev:8,  div:10.8, fcf:null,score:78, conf:"high"   },
  { t:"MOEX", n:"Мосбиржа",   sec:"Финансы",   price:198,   chg:1.1,  mcap:451,  pe:7.0, ev:null,pb:1.9, roe:27, mgn:null,nd:null, rev:14, div:8.9,  fcf:null,score:78, conf:"high"   },
  { t:"NLMK", n:"НЛМК",       sec:"Металлы",   price:142.5, chg:-0.5, mcap:854,  pe:5.8, ev:3.8, pb:1.9, roe:28, mgn:30, nd:0.2,  rev:4,  div:12.3, fcf:12, score:77, conf:"medium" },
  { t:"PLZL", n:"Полюс",      sec:"Металлы",   price:14320, chg:0.9,  mcap:1945, pe:6.8, ev:5.6, pb:3.8, roe:41, mgn:58, nd:1.1,  rev:18, div:5.2,  fcf:8,  score:76, conf:"high"   },
  { t:"CHMF", n:"Северсталь", sec:"Металлы",   price:1284,  chg:-0.7, mcap:1075, pe:6.0, ev:4.2, pb:2.6, roe:33, mgn:33, nd:0.5,  rev:6,  div:11.8, fcf:11, score:75, conf:"medium" },
  { t:"ROSN", n:"Роснефть",   sec:"Нефтегаз",  price:564.20,chg:0.0,  mcap:5980, pe:5.0, ev:3.4, pb:0.71,roe:15, mgn:30, nd:1.3,  rev:2,  div:10.4, fcf:9,  score:74, conf:"medium" },
  { t:"FIVE", n:"X5 Group",   sec:"Ритейл",    price:3210,  chg:0.8,  mcap:871,  pe:8.8, ev:4.0, pb:2.2, roe:25, mgn:8,  nd:1.1,  rev:20, div:0,    fcf:8,  score:72, conf:"medium" },
  { t:"PHOR", n:"ФосАгро",    sec:"Химия",     price:6740,  chg:0.3,  mcap:873,  pe:7.6, ev:6.0, pb:4.1, roe:38, mgn:36, nd:1.4,  rev:3,  div:7.8,  fcf:6,  score:71, conf:"medium" },
  { t:"MGNT", n:"Магнит",     sec:"Ритейл",    price:5104,  chg:-0.4, mcap:520,  pe:9.1, ev:3.9, pb:1.6, roe:18, mgn:7,  nd:1.2,  rev:19, div:9.7,  fcf:7,  score:70, conf:"medium" },
  { t:"YDEX", n:"Яндекс",     sec:"Технологии",price:4188,  chg:2.1,  mcap:1612, pe:16.5,ev:11.2,pb:3.1, roe:14, mgn:18, nd:0.4,  rev:38, div:0,    fcf:2,  score:69, conf:"medium" },
  { t:"MTSS", n:"МТС",        sec:"Телеком",   price:214,   chg:0.2,  mcap:428,  pe:8.4, ev:4.1, pb:6.2, roe:41, mgn:41, nd:1.8,  rev:7,  div:11.9, fcf:9,  score:66, conf:"medium" },
  { t:"GMKN", n:"Норникель",  sec:"Металлы",   price:138.60,chg:-1.6, mcap:2118, pe:7.2, ev:5.1, pb:2.4, roe:22, mgn:44, nd:1.5,  rev:-3, div:6.1,  fcf:7,  score:63, conf:"medium" },
  { t:"SNGS", n:"Сургутнефтегаз",sec:"Нефтегаз",price:26.9, chg:0.1,  mcap:1162, pe:3.2, ev:1.1, pb:0.3, roe:9,  mgn:26, nd:-4.5, rev:1,  div:2.1,  fcf:3,  score:60, conf:"medium" },
  { t:"ALRS", n:"АЛРОСА",     sec:"Металлы",   price:52.4,  chg:-1.2, mcap:386,  pe:6.2, ev:4.4, pb:1.5, roe:19, mgn:40, nd:0.9,  rev:-8, div:9.3,  fcf:5,  score:58, conf:"low"    },
  { t:"GAZP", n:"Газпром",    sec:"Нефтегаз",  price:128.05,chg:-0.8, mcap:3030, pe:3.6, ev:3.1, pb:0.34,roe:6,  mgn:32, nd:1.9,  rev:-4, div:0,    fcf:4,  score:52, conf:"medium" },
  { t:"AFKS", n:"АФК Система", sec:"Холдинг",   price:14.2,  chg:-1.4, mcap:137,  pe:12.0,ev:8.5, pb:1.1, roe:5,  mgn:22, nd:3.9,  rev:11, div:3.5,  fcf:2,  score:48, conf:"low"    },
  { t:"RUAL", n:"РУСАЛ",      sec:"Металлы",   price:34.8,  chg:-0.9, mcap:528,  pe:9.5, ev:7.2, pb:0.7, roe:7,  mgn:12, nd:3.6,  rev:-2, div:0,    fcf:1,  score:45, conf:"low"    },
];

// Metric/criteria definitions. dir: "low" = lower is better, "high" = higher is better.
// dom: [min,max] slider domain (nice rounded, padded around universe).
const METRICS = {
  pe:   { key:"pe",  group:"Оценка",     label:"P / E",            unit:"×", dir:"low",  dom:[0,20],  step:0.1, dec:1 },
  ev:   { key:"ev",  group:"Оценка",     label:"EV / EBITDA",      unit:"×", dir:"low",  dom:[0,12],  step:0.1, dec:1 },
  pb:   { key:"pb",  group:"Оценка",     label:"P / B",            unit:"×", dir:"low",  dom:[0,7],   step:0.05,dec:2 },
  roe:  { key:"roe", group:"Качество",   label:"ROE",              unit:"%", dir:"high", dom:[0,45],  step:1,   dec:0 },
  mgn:  { key:"mgn", group:"Качество",   label:"Рентабельность EBITDA",    unit:"%", dir:"high", dom:[0,65],  step:1,   dec:0 },
  nd:   { key:"nd",  group:"Качество",   label:"Net debt / EBITDA",unit:"×", dir:"low",  dom:[-5,4],  step:0.1, dec:1 },
  rev:  { key:"rev", group:"Рост",       label:"Рост выручки",     unit:"%", dir:"high", dom:[-10,40],step:1,   dec:0 },
  div:  { key:"div", group:"Доходность", label:"Дивдоходность",    unit:"%", dir:"high", dom:[0,14],  step:0.1, dec:1 },
  fcf:  { key:"fcf", group:"Доходность", label:"FCF yield",        unit:"%", dir:"high", dom:[0,16],  step:0.5, dec:0 },
  mcap: { key:"mcap",group:"Размер",     label:"Капитализация",    unit:"",  dir:"high", dom:[0,7000],step:50,  dec:0, money:true },
};
const METRIC_GROUPS = ["Оценка","Качество","Рост","Доходность","Размер"];
const SECTORS = ["Нефтегаз","Металлы","Финансы","Ритейл","Технологии","Химия","Телеком","Холдинг"];

// Table columns shown by default (besides identity + score).
const TABLE_METRICS = ["pe","ev","roe","mgn","nd","div","fcf","rev","mcap"];

// Saved screens. ranges: { metricKey: [lo,hi] }; sectors: optional list.
const PRESETS = [
  { id:"all",   name:"Все бумаги",            desc:"Без фильтров", ranges:{}, sectors:[] },
  { id:"cheapcf",name:"Дешёвый кэшфлоу",      desc:"EV/EBITDA ≤ 4 · FCF yield ≥ 8", ranges:{ ev:[0,4], fcf:[8,16] }, sectors:[] },
  { id:"divcov",name:"Дивиденд с покрытием",  desc:"Дивдоходность ≥ 9% · долг ≤ 1,5×", ranges:{ div:[9,14], nd:[-5,1.5] }, sectors:[] },
  { id:"qgarp", name:"Качество по цене",      desc:"ROE ≥ 20% · P/E ≤ 7", ranges:{ roe:[20,45], pe:[0,7] }, sectors:[] },
  { id:"lowlev",name:"Низкий долг",           desc:"Net debt / EBITDA ≤ 0,5×", ranges:{ nd:[-5,0.5] }, sectors:[] },
  { id:"export",name:"Экспортёры",            desc:"Нефтегаз и металлы", ranges:{}, sectors:["Нефтегаз","Металлы"] },
];

// One-line Basis thesis per ticker (illustrative, decision-support not advice).
const THESIS = {
  TATN:"Низкая оценка при высоком ROE и почти нулевом долге; дивиденд хорошо покрыт.",
  LKOH:"Сильный FCF и чистая денежная позиция; качество по разумной цене.",
  NVTK:"Премиальная маржа СПГ; оценка выше сектора, основной драйвер — проекты роста.",
  SBER:"Дешёвый по прибыли банк с устойчивым ROE; данные по EV/марже неприменимы.",
  MOEX:"Структурный бенефициар высокой ставки; стабильный ROE, низкая капиталоёмкость.",
  NLMK:"Дешёвый экспортёр с высокой маржой и низким долгом; чувствителен к ценам стали.",
  PLZL:"Лучшая в классе маржа и ROE; оценка выше из-за качества активов.",
  CHMF:"Высокий ROE и щедрый дивиденд; цикличность стального рынка — главный риск.",
  ROSN:"Дисконт к мейджорам отражает страновой риск; «Восток Ойл» — драйвер стоимости.",
  FIVE:"Быстрый рост выручки, тонкая маржа ритейла; дивиденд пока не платится.",
  PHOR:"Высокий ROE и маржа в удобрениях; оценка по P/B повышенная.",
  MGNT:"Рост сети и приемлемый дивиденд; маржа структурно низкая для ритейла.",
  YDEX:"Самый быстрый рост в выборке; оценка premium, денежный поток пока скромный.",
  MTSS:"Высокий дивиденд и ROE, но высокий долг и P/B; защитный кэшфлоу телекома.",
  GMKN:"Высокая маржа, но падение выручки и капзатраты давят на FCF и дивиденд.",
  SNGS:"Глубокий дисконт и денежная подушка; вопрос — раскрытие стоимости для миноритариев.",
  ALRS:"Слабый цикл алмазов: падение выручки и низкая уверенность в прогнозах.",
  GAZP:"Низкая оценка отражает слабую выручку, нулевой дивиденд и высокий долг.",
  AFKS:"Холдинговый дисконт и высокий долг; стоимость зависит от IPO дочерних компаний.",
  RUAL:"Низкая маржа и высокий долг; оценка низкая, но качество и FCF слабые.",
};

// ---- analytics helpers ----
function vals(key){ return UNIVERSE.map(r=>r[key]).filter(v=>v!=null); }

// percentile of value within universe in the "good" direction → 0..1 (1 = best)
function goodPct(key, v){
  if(v==null) return null;
  const m=METRICS[key]; const arr=vals(key);
  const below = arr.filter(x=> x < v).length;
  let p = below / (arr.length-1 || 1);
  return m.dir==="low" ? 1-p : p;
}
// raw position 0..1 across domain (for cell bar geometry)
function domPos(key, v){ const [a,b]=METRICS[key].dom; return Math.max(0,Math.min(1,(v-a)/(b-a))); }

function histogram(key, buckets=18){
  const m=METRICS[key]; const [a,b]=m.dom; const arr=vals(key);
  const h=new Array(buckets).fill(0);
  arr.forEach(v=>{ let i=Math.floor((v-a)/(b-a)*buckets); i=Math.max(0,Math.min(buckets-1,i)); h[i]++; });
  return h;
}

function matchesRanges(row, ranges){
  for(const k in ranges){
    const [lo,hi]=ranges[k]; const v=row[k];
    if(v==null) return false;            // honest: N/A fails an active metric filter
    if(v<lo-1e-9 || v>hi+1e-9) return false;
  }
  return true;
}
function applyScreen(ranges, sectors){
  return UNIVERSE.filter(r=>
    matchesRanges(r,ranges) && (!sectors||sectors.length===0||sectors.includes(r.sec))
  );
}

const SECTOR_COLORS = {
  "Нефтегаз":"var(--accent)", "Металлы":"var(--violet)", "Финансы":"var(--info)",
  "Ритейл":"var(--amber)", "Технологии":"#3FA7C4", "Химия":"var(--pos)",
  "Телеком":"#C77DBB", "Холдинг":"var(--ink-3)",
};

// Continuous Basis-score color: red (low) → orange (mid) → green (high).
// Piecewise hue 0(red)→33(orange)→138(green) so the orange "hold" band reads true.
function scoreColor(s){
  const t = Math.max(0, Math.min(1, (s-45)/(82-45)));
  const hue = t < 0.5 ? (t/0.5)*33 : 33 + ((t-0.5)/0.5)*105;
  return `hsl(${hue.toFixed(0)} 64% 39%)`;
}

// Axis options for the map: Basis score + every screener metric.
function axisDef(key){
  if(key==="score") return { key:"score", label:"Basis-балл", unit:"", dom:[42,84], get:(r)=>r.score, dir:"high" };
  const M=METRICS[key];
  return { key, label:M.label, unit:M.unit, dom:M.dom, get:(r)=>r[key], dir:M.dir, money:M.money };
}
const AXIS_KEYS = ["score", ...Object.keys(METRICS)];

Object.assign(window, {
  SC_NB:NB, SC_UNIVERSE:UNIVERSE, SC_METRICS:METRICS, SC_METRIC_GROUPS:METRIC_GROUPS,
  SC_SECTORS:SECTORS, SC_TABLE_METRICS:TABLE_METRICS, SC_PRESETS:PRESETS, SC_THESIS:THESIS,
  SC_SECTOR_COLORS:SECTOR_COLORS, SC_AXIS_KEYS:AXIS_KEYS,
  scNum:num, scMoney:money, scVals:vals, scGoodPct:goodPct, scDomPos:domPos,
  scHistogram:histogram, scApply:applyScreen, scMatchesRanges:matchesRanges,
  scScoreColor:scoreColor, scAxisDef:axisDef,
});
