// Basis Market — data for all asset classes + helpers. Exported to window.
// Illustrative mock data (ru-RU). Not real quotes.
const NB="\u00A0", NN="\u202F";
function grp(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NN); }
function num(v,d=2){ if(v==null) return "—"; const s=v.toFixed(d).replace(".",","); const [i,f]=s.split(","); return grp(i)+(f?","+f:""); }
function money(v){ if(v==null) return "—"; if(v>=1000) return num(v/1000,2)+NB+"трлн"+NB+"₽"; return grp(Math.round(v*10)/10).replace(".",",")+NB+"млрд"+NB+"₽"; }

// ===== STOCKS — grouped by sector =====
const STOCK_SECTORS = ["Нефть и газ","Финансы","Металлургия","IT-сектор","Потребительский сектор","Телеком","Электроэнергетика","Химия","Девелопмент","Транспорт","Прочее"];
// tone: композитный тон Basis (buy-ish→sell-ish, шкала качество/оценка). 0..100, цвет на градиенте.
const STOCKS = [
  { t:"ROSN", n:"Роснефть", sec:"Нефть и газ", price:564.20, chg:0.0,  chgAbs:0.0,  mcap:5980, tone:74, conf:"medium" },
  { t:"LKOH", n:"Лукойл",   sec:"Нефть и газ", price:7412,   chg:0.3,  chgAbs:22,   mcap:5134, tone:81, conf:"high" },
  { t:"NVTK", n:"Новатэк",  sec:"Нефть и газ", price:978.4,  chg:-2.14,chgAbs:-21.4,mcap:3024, tone:79, conf:"high" },
  { t:"GAZP", n:"Газпром",  sec:"Нефть и газ", price:104.49, chg:-2.07,chgAbs:-2.21,mcap:2475, tone:52, conf:"medium" },
  { t:"SIBN", n:"Газпром нефть", sec:"Нефть и газ", price:459.75, chg:-0.50,chgAbs:-2.3, mcap:2179, tone:70, conf:"medium" },
  { t:"TATN", n:"Татнефть", sec:"Нефть и газ", price:648,    chg:0.4,  chgAbs:2.6,  mcap:1505, tone:80, conf:"high" },
  { t:"SNGS", n:"Сургутнефтегаз", sec:"Нефть и газ", price:26.9, chg:0.1, chgAbs:0.03, mcap:1162, tone:60, conf:"medium" },
  { t:"SBER", n:"Сбербанк", sec:"Финансы", price:317.82, chg:1.4, chgAbs:4.4, mcap:6845, tone:78, conf:"high" },
  { t:"VTBR", n:"ВТБ",      sec:"Финансы", price:98.2,   chg:0.6, chgAbs:0.59, mcap:530, tone:54, conf:"low" },
  { t:"MOEX", n:"Мосбиржа", sec:"Финансы", price:198,    chg:1.1, chgAbs:2.15, mcap:451, tone:78, conf:"high" },
  { t:"GMKN", n:"Норникель", sec:"Металлургия", price:138.60, chg:-1.6, chgAbs:-2.25, mcap:2118, tone:63, conf:"medium" },
  { t:"PLZL", n:"Полюс",    sec:"Металлургия", price:14320, chg:0.9, chgAbs:128, mcap:1945, tone:76, conf:"high" },
  { t:"CHMF", n:"Северсталь", sec:"Металлургия", price:1284, chg:-0.7, chgAbs:-9, mcap:1075, tone:75, conf:"medium" },
  { t:"NLMK", n:"НЛМК",     sec:"Металлургия", price:142.5, chg:-0.5, chgAbs:-0.72, mcap:854, tone:77, conf:"medium" },
  { t:"YDEX", n:"Яндекс",   sec:"IT-сектор", price:4188, chg:2.1, chgAbs:86, mcap:1612, tone:69, conf:"medium" },
  { t:"OZON", n:"Озон",     sec:"IT-сектор", price:3640, chg:1.6, chgAbs:57, mcap:786, tone:61, conf:"low" },
  { t:"FIVE", n:"X5 Group", sec:"Потребительский сектор", price:3210, chg:0.8, chgAbs:25, mcap:871, tone:72, conf:"medium" },
  { t:"MGNT", n:"Магнит",   sec:"Потребительский сектор", price:5104, chg:-0.4, chgAbs:-20, mcap:520, tone:70, conf:"medium" },
  { t:"MTSS", n:"МТС",      sec:"Телеком", price:214, chg:0.2, chgAbs:0.43, mcap:428, tone:66, conf:"medium" },
  { t:"PHOR", n:"ФосАгро",  sec:"Химия", price:6740, chg:0.3, chgAbs:20, mcap:873, tone:71, conf:"medium" },
  { t:"IRAO", n:"Интер РАО", sec:"Электроэнергетика", price:3.92, chg:0.5, chgAbs:0.02, mcap:409, tone:64, conf:"medium" },
  { t:"PIKK", n:"ПИК",      sec:"Девелопмент", price:548, chg:-1.1, chgAbs:-6.1, mcap:362, tone:55, conf:"low" },
];

// ===== BONDS =====
const BOND_RELI = { high:{label:"Надёжный",tone:"pos"}, mid:{label:"Средний",tone:"amber"}, vdo:{label:"ВДО",tone:"neg"} };
const BONDS = [
  { t:"Газпнф3P2R", isin:"RU000A1017J5", n:"Газпром нефть БО 003P-02R", reli:"high", agency:"AAA", basis:"AAA-AA", spread:83,  ytm:14.8, dur:3.0, price:81.5,  mat:"2029-12-07", coupon:"Фикс" },
  { t:"РЖД 1Р-26R", isin:"RU000A108KR0", n:"РЖД 001P-26R", reli:"high", agency:"AAA", basis:"AAA-AA", spread:78,  ytm:15.1, dur:2.4, price:95.2,  mat:"2030-04-18", coupon:"Фикс" },
  { t:"Сбер Sb44R", isin:"RU000A109BR1", n:"Сбербанк 001Р-SBER44R", reli:"high", agency:"AAA", basis:"AAA-AA", spread:64,  ytm:14.6, dur:1.9, price:99.1,  mat:"2028-09-12", coupon:"Флоатер" },
  { t:"МТС 2P-05", isin:"RU000A105KR8", n:"МТС 002P-05", reli:"high", agency:"AA+", basis:"A", spread:121, ytm:15.7, dur:2.1, price:97.4,  mat:"2029-03-29", coupon:"Фикс" },
  { t:"ВУШ 001P-04", isin:"RU000A106HB4", n:"Whoosh 001P-04", reli:"mid", agency:"A-", basis:"BBB", spread:288, ytm:18.9, dur:1.6, price:96.0,  mat:"2027-07-02", coupon:"Фикс" },
  { t:"Сегежа2P5R", isin:"RU000A105SP3", n:"Сегежа 002P-05R", reli:"vdo", agency:"BBB", basis:"B+", spread:920, ytm:27.4, dur:1.1, price:88.3,  mat:"2026-12-14", coupon:"Фикс" },
  { t:"ЭталФ 2P3", isin:"RU000A105VU7", n:"Эталон-Финанс 002P-03", reli:"mid", agency:"A-", basis:"BBB", spread:340, ytm:19.6, dur:2.2, price:93.7,  mat:"2028-05-16", coupon:"Фикс" },
  { t:"АФКСис1P30", isin:"RU000A108GP6", n:"АФК Система 001P-30", reli:"mid", agency:"AA-", basis:"BBB+", spread:265, ytm:18.2, dur:1.4, price:98.5,  mat:"2027-02-20", coupon:"Флоатер" },
];

// ===== FUTURES =====
const FUT_GROUPS = ["Валюта","Индексы","Сырьё","На акции"];
const FUTURES = [
  { t:"CNY-9.26", n:"Китайский юань / рубль", grp:"Валюта", lev:10.1, exp:88,  go:1100, nominal:11076, oi:37051276 },
  { t:"Si-9.26",  n:"Доллар США / рубль",     grp:"Валюта", lev:6.5,  exp:88,  go:11642,nominal:75361, oi:11115886 },
  { t:"Eu-9.26",  n:"Евро / рубль",           grp:"Валюта", lev:6.4,  exp:88,  go:13490,nominal:86690, oi:1846834 },
  { t:"CNY-12.26",n:"Китайский юань / рубль",  grp:"Валюта", lev:10.2, exp:179, go:1107, nominal:11327, oi:809384 },
  { t:"ED-9.26",  n:"Евро / доллар",          grp:"Валюта", lev:15.0, exp:88,  go:5604, nominal:84238, oi:715830 },
  { t:"MIX-9.26", n:"Индекс МосБиржи",        grp:"Индексы",lev:7.2,  exp:88,  go:38500,nominal:277200,oi:842110 },
  { t:"RTS-9.26", n:"Индекс РТС",             grp:"Индексы",lev:8.1,  exp:88,  go:21400,nominal:173000,oi:1204556 },
  { t:"BR-8.26",  n:"Нефть Brent",            grp:"Сырьё",  lev:9.4,  exp:58,  go:7200, nominal:67700, oi:512300 },
  { t:"GD-9.26",  n:"Золото",                 grp:"Сырьё",  lev:6.8,  exp:88,  go:24100,nominal:163800,oi:288940 },
  { t:"SBRF-9.26",n:"Сбербанк",               grp:"На акции",lev:5.6, exp:88,  go:6850, nominal:38200, oi:967300 },
  { t:"GAZR-9.26",n:"Газпром",                grp:"На акции",lev:6.1, exp:88,  go:1880, nominal:10449, oi:1320880 },
];

// ===== FUNDS (ETF/БПИФ) =====
const FUND_GROUPS = ["Акции","Облигации","Денежный рынок","Золото","Смешанные"];
const FUNDS = [
  { t:"TMOS", n:"Т-Капитал Индекс МосБиржи", grp:"Акции", price:8.42, chg:0.7, ter:0.79, nav:48.2, track:"Индекс МосБиржи" },
  { t:"SBMX", n:"Первая — Индекс МосБиржи",   grp:"Акции", price:21.7, chg:0.6, ter:1.00, nav:112.4, track:"Индекс МосБиржи" },
  { t:"EQMX", n:"ВИМ — Индекс МосБиржи",      grp:"Акции", price:182.3,chg:0.65,ter:0.67, nav:96.1, track:"Индекс МосБиржи" },
  { t:"OBLG", n:"ВИМ — Корп. облигации",      grp:"Облигации", price:118.9, chg:0.1, ter:0.45, nav:71.3, track:"Корп. облигации" },
  { t:"SBGB", n:"Первая — ОФЗ",               grp:"Облигации", price:14.2, chg:0.05, ter:0.82, nav:39.8, track:"Индекс ОФЗ" },
  { t:"LQDT", n:"ВИМ — Ликвидность",          grp:"Денежный рынок", price:1.51, chg:0.06, ter:0.40, nav:312.6, track:"RUSFAR" },
  { t:"SBMM", n:"Первая — Сберегательный",    grp:"Денежный рынок", price:13.1, chg:0.06, ter:0.50, nav:204.9, track:"RUSFAR" },
  { t:"GOLD", n:"ВИМ — Золото",               grp:"Золото", price:1.84, chg:-1.1, ter:0.66, nav:54.1, track:"Цена золота" },
];

// ===== CURRENCY & METALS =====
const FX = [
  { n:"Китайский юань / рубль", t:"CNYRUB", price:10.807, chg:0.16 },
  { n:"Доллар США / рубль",     t:"USDRUB", price:73.793, chg:0.33 },
];
const METALS = [
  { n:"Золото / рубль (грамм)",   t:"GLDRUB", price:9720.60, chg:-1.15 },
  { n:"Палладий / рубль (грамм)", t:"PLDRUB", price:2943.00, chg:-1.03 },
  { n:"Платина / рубль (грамм)",  t:"PLTRUB", price:3939.90, chg:-1.92 },
  { n:"Серебро / рубль (грамм)",  t:"SLVRUB", price:153.96,  chg:-1.56 },
];

// ===== MARKET PULSE — index + cross-asset drivers =====
const INDEX = { name:"Индекс МосБиржи", ticker:"IMOEX", level:2847.3, chg:0.62,
  spark:[2798,2812,2805,2824,2818,2831,2820,2826,2839,2833,2842,2847] };
// drivers: dir 1/-1/0 = market move ▲/▼/▬; effect = Basis reasoning (not advice)
const DRIVERS = [
  { name:"Нефть Brent", val:"68,4 $",  dir:1,  effect:"поддержка нефтегазу" },
  { name:"USD / RUB",   val:"73,79",   dir:1,  effect:"плюс экспортёрам" },
  { name:"Ставка ЦБ",   val:"18,0 %",  dir:0,  effect:"давит на оценки" },
  { name:"ОФЗ 10 лет",  val:"15,1 %",  dir:1,  effect:"конкурент акциям" },
];
const MARKET_TONE = { label:"Осторожный аппетит к риску", tone:62 };

const SECTOR_COLORS = {
  "Нефть и газ":"#C2792E", "Финансы":"#1F8A5B", "Металлургия":"#7C6FE0", "IT-сектор":"#2A6FDB",
  "Потребительский сектор":"#C44B9E", "Телеком":"#3FA7C4", "Электроэнергетика":"#D9A441",
  "Химия":"#5B9E4B", "Девелопмент":"#B2643A", "Транспорт":"#6B7A8F", "Прочее":"#857D6F",
};

// tone → color on a continuous green→amber→red gradient (good→neutral→weak)
function toneColor(t){ // 0..100, high=good=green
  const x=Math.max(0,Math.min(100,t))/100;
  // green hsl(145,55,40) → amber hsl(38,80,48) → red hsl(352,60,52)
  let h,s,l;
  if(x>=0.5){ const k=(x-0.5)/0.5; h=38+(145-38)*k; s=80-(80-52)*k; l=48-(48-40)*k; }
  else { const k=x/0.5; h=352+(38-352)*k; s=60+(80-60)*k; l=52-(52-48)*k; }
  return `hsl(${h.toFixed(0)} ${s.toFixed(0)}% ${l.toFixed(0)}%)`;
}

// fair-value upside (%) → continuous color: green (above current) → orange (~0) → red (below)
function fvColor(fv){
  const t=Math.max(-1,Math.min(1,fv/25));
  if(t>=0){ return `hsl(${(40+108*t).toFixed(0)} ${(80-25*t).toFixed(0)}% ${(48-8*t).toFixed(0)}%)`; }
  const k=-t, h=((40-48*k)%360+360)%360; return `hsl(${h.toFixed(0)} ${(80-18*k).toFixed(0)}% ${(48+4*k).toFixed(0)}%)`;
}

Object.assign(window, {
  MK_NB:NB, mkNum:num, mkMoney:money, mkGrp:grp, mkFvColor:fvColor,
  MK_STOCK_SECTORS:STOCK_SECTORS, MK_STOCKS:STOCKS,
  MK_BONDS:BONDS, MK_BOND_RELI:BOND_RELI,
  MK_FUT_GROUPS:FUT_GROUPS, MK_FUTURES:FUTURES,
  MK_FUND_GROUPS:FUND_GROUPS, MK_FUNDS:FUNDS,
  MK_FX:FX, MK_METALS:METALS,
  MK_SECTOR_COLORS:SECTOR_COLORS, mkToneColor:toneColor,
  MK_INDEX:INDEX, MK_DRIVERS:DRIVERS, MK_MARKET_TONE:MARKET_TONE,
});
