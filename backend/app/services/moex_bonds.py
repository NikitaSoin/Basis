"""Облигации с MOEX ISS (класс активов «Облигации»).

Список и параметры:
  /iss/engines/stock/markets/bonds/boards/{BOARD}/securities.json
  блоки securities (параметры выпуска) + marketdata (YTM, дюрация, цена).
Боард: TQOB — ОФЗ, TQCB — корпоративные (рынок T+, основной режим).

Оценка надёжности (НАШ подход, методика — docs/bonds-methodology.md):
  агентских рейтингов в ISS нет, поэтому за ночной срез риск-тир оцениваем по
  СПРЕДУ YTM к кривой ОФЗ (G-curve/ZCYC) той же дюрации:
    ОФЗ              → gov          (госдолг, риск дефолта минимальный)
    спред  < 250 б.п.→ high         (надёжный корпорат)
    250–600 б.п.     → medium       (средний риск)
    > 600 б.п.       → speculative  (ВДО — высокая доходность как плата за риск)
  Это ОЦЕНКА, не агентский рейтинг — помечаем в карточке. Реальные рейтинги
  АКРА/Эксперт РА — следующий шаг (ОК владельца).
"""
import json
import logging
import re
import ssl
import time
import urllib.request
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}

# Борды рынка облигаций MOEX с осмысленными рыночными данными (YTM/дюрация/цена).
# TQOB — ОФЗ ₽; TQCB — корпораты/биржевые/субфед/муни ₽; TQOY — юаневые; TQOD — USD;
# TQRD — режим Д (дефолтные/проблемные, важно для честной надёжности).
TRADE_BOARDS = [("TQOB", "ofz"), ("TQCB", "corporate"),
                ("TQOY", "corporate"), ("TQOD", "corporate"), ("TQRD", "corporate")]

BONDS_URL = ("https://iss.moex.com/iss/engines/stock/markets/bonds/boards/{board}/securities.json"
             "?iss.meta=off&iss.only=securities,marketdata"
             "&securities.columns=SECID,SHORTNAME,ISIN,MATDATE,OFFERDATE,COUPONVALUE,COUPONPERCENT,"
             "COUPONPERIOD,FACEVALUE,FACEUNIT,ACCRUEDINT,LOTSIZE,LISTLEVEL,SECTYPE,EMITENT_TITLE"
             "&marketdata.columns=SECID,LAST,LCURRENTPRICE,YIELD,DURATION")
ZCYC_URL = "https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as r:
        return json.loads(r.read())


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _d(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").date() if v and v != "0000-00-00" else None
    except ValueError:
        return None


def load_ofz_curve() -> list[tuple[float, float]]:
    """Точки кривой ОФЗ (срок в годах, доходность %) — для спреда корпоратов."""
    try:
        data = _get(ZCYC_URL)
        cols = data["yearyields"]["columns"]
        rows = [dict(zip(cols, r)) for r in data["yearyields"]["data"]]
        return sorted((float(r["period"]), float(r["value"])) for r in rows if r.get("value") is not None)
    except Exception as e:
        logger.warning("ОФЗ-кривая недоступна: %s", e)
        return []


def ofz_yield_at(curve: list[tuple[float, float]], years: float) -> float | None:
    """Доходность ОФЗ на срок `years` — линейная интерполяция по кривой."""
    if not curve or years is None:
        return None
    if years <= curve[0][0]:
        return curve[0][1]
    if years >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= years <= x1:
            return y0 + (y1 - y0) * (years - x0) / (x1 - x0)
    return None


def classify_risk(bond_type: str, spread_bp: int | None) -> str | None:
    if bond_type == "ofz":
        return "gov"
    if spread_bp is None:
        return None   # нет YTM/дюрации → нет рыночной оценки (честно, не «medium»)
    if spread_bp < 250:
        return "high"
    if spread_bp <= 600:
        return "medium"
    return "speculative"


# Связка выпуск → эмитент-компания в нашей базе. Матч по подстроке в имени
# выпуска (поле NAME описания MOEX, напр. «ПАО НК Роснефть 002P-06»). Порядок
# важен: более специфичные ключи выше (Газпром нефть прежде Газпром). Покрывает
# крупных публичных эмитентов — у них есть financials.json для оценки долга;
# мелкие/ВДО эмитенты не публичны (нет в базе) → разбираются bond-analyst.
ISSUER_TICKER_MAP = [
    ("газпром нефть", "SIBN"), ("газпромнефть", "SIBN"),
    ("газпром", "GAZP"), ("роснефть", "ROSN"), ("лукойл", "LKOH"),
    ("газпромбанк", "GAZP"),  # ГПБ — дочка Газпрома (грубо)
    ("сбербанк", "SBER"), ("сбер", "SBER"),
    ("втб", "VTBR"), ("система", "AFKS"),
    ("мобильные телесистемы", "MTSS"), ("мтс-банк", "MBNK"),
    ("ростелеком", "RTKM"), ("магнит", "MGNT"), ("северсталь", "CHMF"),
    ("нлмк", "NLMK"), ("новолипецк", "NLMK"), ("алроса", "ALRS"),
    ("транснефть", "TRNFP"), ("татнефть", "TATN"), ("сегежа", "SGZH"),
    ("самолет", "SMLT"), ("аэрофлот", "AFLT"), ("совкомфлот", "FLOT"),
    ("русгидро", "HYDR"), ("россети", "FEES"), ("фосагро", "PHOR"),
    ("европлан", "LEAS"), ("эталон", "ETLN"),
    ("норильский никель", "GMKN"), ("норникель", "GMKN"), ("гмк", "GMKN"),
    ("полюс", "PLZL"), ("камаз", "KMAZ"), ("соллерс", "SVAV"),
    ("совкомбанк", "SVCB"), ("хэдхантер", "HEAD"), ("хедхантер", "HEAD"),
    ("новабев", "BELU"), ("белуга", "BELU"), ("позитив", "POSI"),
    ("озон", "OZON"), ("яндекс", "YDEX"), ("вуш", "WUSH"), ("whoosh", "WUSH"),
    ("делимобиль", "DELI"), ("каршеринг", "DELI"),
    ("россельхозбанк", "RSHB"), ("альфа-банк", "ALFA"),
    ("пик", "PIKK"), ("лср", "LSRG"), ("мечел", "MTLR"),
    ("ленэнерго", "LSNG"), ("мосэнерго", "MSNG"), ("огк-2", "OGKB"),
    ("юнипро", "UPRO"), ("фск", "FEES"), ("россети", "FEES"),
    ("тмк", "TRMK"), ("трубная металлургическая", "TRMK"),
]


# Авто-связка: имя выпуска → публичная компания из нашей базы (companies). Курируемая
# карта ловит крупных, но компаний 262 — остальных доберём нормализацией имени.
# Кэш строится один раз из БД (build_company_keys), матч — по целому слову.
_COMPANY_KEYS: list[tuple[str, str]] = []   # [(нормализованный ключ, ticker)], длинные раньше

# Слишком общие/короткие ключи, дающие ложные совпадения — не матчим по ним.
_KEY_STOPLIST = {"система", "группа", "финанс", "капитал", "инвест", "русские",
                 "первый", "регион", "центр", "восток", "запад", "юг", "сибирь"}


# латинские буквы-двойники → кириллица (MOEX иногда мешает раскладки в именах выпусков)
_LAT2CYR = str.maketrans({
    "A": "А", "a": "а", "B": "В", "C": "С", "c": "с", "E": "Е", "e": "е",
    "H": "Н", "K": "К", "k": "к", "M": "М", "O": "О", "o": "о", "P": "Р",
    "p": "р", "T": "Т", "X": "Х", "x": "х", "y": "у", "Y": "У",
})


def _norm_issuer(s: str | None) -> str:
    """Нормализация имени для матчинга: убрать орг-формы, кавычки, пунктуацию."""
    if not s:
        return ""
    s = s.translate(_LAT2CYR)  # латинские двойники в кириллице (напр. БO-02 с латинской O) → кириллица
    s = re.sub(r"\s+", " ", s.lower())   # схлопнуть пробелы ДО удаления орг-форм (двойные пробелы в именах MOEX)
    for w in ("публичное акционерное общество", "акционерное общество",
              "общество с ограниченной ответственностью", "коммерческий банк",
              " пао", " оао", " ооо", " ао ", " нао", " зао", "пао ", "оао ", "ооо "):
        s = s.replace(w, " ")
    s = re.sub(r"[\"«»()\,\.\-–—_]", " ", s)
    # разлепить склеенные «имя+серия» (ТАЛКлизинг001P-03 → талклизинг 001 p 03)
    s = re.sub(r"(?<=[а-яёa-z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[а-яёa-z])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_SERIES_DIGIT = re.compile(r"\d")
_SERIES_DROP = {"бо", "об", "обл", "серия", "сер", "класс", "выпуск", "п", "r",
                "пк", "биржевые", "облигации", "ин", "ра", "ао", "пбо", "оа",
                "р", "рс", "кл", "об"}


def issuer_slug(name: str | None) -> str | None:
    """Стабильный слаг ЭМИТЕНТА из имени выпуска (без серии). Группирует все серии
    одного эмитента → один профиль бизнеса/финансов на эмитента. Напр.
    «ГПБ (АО) БО 004Р-26» и «ГПБ (АО) БО 001Р-26Р» → 'гпб'."""
    k = _norm_issuer(name)
    words = [w for w in k.split()
             if w and len(w) > 1 and not _SERIES_DIGIT.search(w) and w not in _SERIES_DROP]
    return "-".join(words) if words else None


def build_company_keys(db) -> None:
    """Заполнить кэш ключей публичных компаний из таблицы companies (один раз)."""
    global _COMPANY_KEYS
    rows = db.execute(text("SELECT ticker, name FROM companies")).all()
    keys: list[tuple[str, str]] = []
    for ticker, name in rows:
        k = _norm_issuer(name)
        # берём первые 1-2 значимых слова как ключ (точнее, чем всё имя)
        if len(k) < 5 or k in _KEY_STOPLIST:
            continue
        keys.append((k, ticker))
    # длинные ключи раньше — более специфичные матчатся первыми
    keys.sort(key=lambda kt: len(kt[0]), reverse=True)
    _COMPANY_KEYS = keys
    logger.info("Авто-связка эмитентов: загружено %d ключей компаний", len(keys))


def match_issuer_ticker(name: str | None, allow_auto: bool = True) -> str | None:
    """Тикер компании-эмитента по имени выпуска (NAME из MOEX). Сначала курируемая
    карта (надёжно), затем авто-матч против ключей компаний из БД (если allow_auto).
    None — мелкий/непубличный эмитент (доберётся кампанией bond-analyst)."""
    if not name:
        return None
    s = name.lower()
    for key, ticker in ISSUER_TICKER_MAP:
        if key in s:
            return ticker
    if allow_auto and _COMPANY_KEYS:
        ln = " " + _norm_issuer(name) + " "
        for key, ticker in _COMPANY_KEYS:
            if " " + key + " " in ln:
                return ticker
    return None


def map_coupon_type(bond_type_raw: str | None) -> str:
    """Тип купона из поля BOND_TYPE описания выпуска MOEX.

    «Флоатер» → floater (плавающая ставка к КС/RUONIA — проц. риска почти нет);
    «Линкер…»  → linker (номинал индексируется на инфляцию — ОФЗ-ИН);
    «Фикс…»    → fixed (постоянный/заранее известный купон);
    иначе      → other.
    """
    if not bond_type_raw:
        return "other"
    s = bond_type_raw.lower()
    if "флоат" in s or "плавающ" in s or "переменн" in s:
        return "floater"
    if "линкер" in s or "индексир" in s:
        return "linker"
    # «Структурная облигация» — выплата привязана к формуле/событию; тело может
    # быть НЕ защищено. Это отдельный, более рисковый класс — помечаем явно.
    if "структурн" in s:
        return "structured"
    # «Валютные облигации» — про валюту номинала (она в currency), не про купон;
    # «Амортизируемые» — про возврат тела частями (это в has_amortization), купон
    # при этом фиксированный. Оба по процентному риску ведут себя как фикс.
    if "фикс" in s or "постоянн" in s or "валютн" in s or "амортиз" in s:
        return "fixed"
    return "other"


def map_ytm_kind(subtype_raw: str | None) -> str | None:
    """Метка вида доходности из BOND_SUBTYPE: к погашению / к оферте."""
    if not subtype_raw:
        return None
    return "к оферте" if "оферт" in subtype_raw.lower() else "к погашению"


# муниципальные/субфедеральные торгуются на TQCB вместе с корпоратами — их класс
# виден только в глобальном type выпуска (subfederal_bond/municipal_bond)
_MUNI_TYPES = {"subfederal_bond", "municipal_bond"}


def fetch_meta_map(secids: list[str], sleep: float = 0.3) -> dict[str, dict]:
    """Тип купона / метка YTM / класс / дефолт по каждому выпуску — из описания
    MOEX (per-security). Последовательно, с паузой (бережно к rate limit).
    Возвращает {secid: {coupon_type, ytm_kind, glob_type, defaulted}}."""
    out: dict[str, dict] = {}
    for i, secid in enumerate(secids):
        try:
            d = _get(f"https://iss.moex.com/iss/securities/{secid}.json?iss.meta=off&iss.only=description")
            m = {r[0]: r[2] for r in d["description"]["data"]}
            out[secid] = {
                "coupon_type": map_coupon_type(m.get("BOND_TYPE")),
                "ytm_kind": map_ytm_kind(m.get("BOND_SUBTYPE")),
                "glob_type": m.get("TYPE"),
                "defaulted": str(m.get("HASDEFAULT")) in ("1", "True"),
                "name": m.get("NAME"),   # полное имя выпуска с эмитентом → связка с компанией
            }
        except Exception as e:
            if "429" in str(e) or "too many" in str(e).lower():
                logger.warning("rate limit на %s — пауза 30с", secid)
                time.sleep(30)
            else:
                logger.warning("описание %s недоступно: %s", secid, e)
            out[secid] = {}
        if (i + 1) % 200 == 0:
            logger.info("  описания: %d/%d", i + 1, len(secids))
        time.sleep(sleep)
    return out


# ── Агентский рейтинг (вторая, независимая от спреда оценка надёжности) ──
# Источник — smart-lab.ru: агрегированный по нац. шкале рейтинг (сводит АКРА /
# Эксперт РА / НКР / НРА в одну букву). Это вторая опора «двойного рейтинга»;
# точное агентство/дата — следующий шаг (per-issue у bond-analyst).
_RATING_RE = re.compile(r"(RU000[A-Z0-9]{7}|SU[0-9A-Z]{10})")
_VALID_RATING = re.compile(r"^(AAA|AA|A|BBB|BB|B|CCC|CC|C|D|RD|SD)[+-]?$", re.I)


def load_agency_ratings(max_pages: int = 20, sleep: float = 0.6) -> dict[str, tuple[str, str]]:
    """ISIN → (рейтинг, источник) со списка облигаций smart-lab (нац. шкала)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    out: dict[str, tuple[str, str]] = {}
    for n in range(1, max_pages + 1):
        url = ("https://smart-lab.ru/q/bonds/order_by_yield/desc/"
               + (f"page{n}/" if n > 1 else ""))
        try:
            req = urllib.request.Request(url, headers=headers)
            html = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx).read().decode("utf-8", "ignore")
        except Exception as e:
            logger.warning("smart-lab page%d недоступна: %s", n, e)
            break
        page_hits = 0
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 8:
                continue
            m = _RATING_RE.search(tr)
            if not m:
                continue
            rating = re.sub("<.*?>", "", tds[7]).strip()
            if rating and _VALID_RATING.match(rating):
                out[m.group(1)] = (rating.upper(), "smart-lab (агрегат агентств)")
                page_hits += 1
        if page_hits == 0:
            break
        time.sleep(sleep)
    logger.info("Агентские рейтинги: %d выпусков", len(out))
    return out


def fetch_board(board: str, bond_type: str) -> list[dict]:
    """Сырые записи облигаций одного борда (объединяет securities + marketdata)."""
    data = _get(BONDS_URL.format(board=board))
    sc, md = data["securities"], data["marketdata"]
    md_map = {r[md["columns"].index("SECID")]: dict(zip(md["columns"], r)) for r in md["data"]}
    out = []
    for row in sc["data"]:
        s = dict(zip(sc["columns"], row))
        m = md_map.get(s["SECID"], {})
        out.append({"s": s, "m": m, "board": board, "bond_type": bond_type})
    return out


_UPSERT = text("""
    INSERT INTO bonds (secid, isin, short_name, issuer_name, issuer_ticker, bond_type, board, currency,
        face_value, coupon_percent, coupon_value, coupon_period, maturity_date, offer_date,
        has_amortization, lot_size, listing_level, last_price, ytm, duration_days, accrued_int,
        coupon_type, ytm_kind, is_defaulted, risk_tier, spread_bp, agency_rating,
        agency_rating_source, updated_at)
    VALUES (:secid, :isin, :short_name, :issuer_name, :issuer_ticker, :bond_type, :board, :currency,
        :face_value, :coupon_percent, :coupon_value, :coupon_period, :maturity_date, :offer_date,
        :has_amortization, :lot_size, :listing_level, :last_price, :ytm, :duration_days, :accrued_int,
        :coupon_type, :ytm_kind, :is_defaulted, :risk_tier, :spread_bp, :agency_rating,
        :agency_rating_source, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        short_name=EXCLUDED.short_name, issuer_name=EXCLUDED.issuer_name,
        issuer_ticker=EXCLUDED.issuer_ticker, bond_type=EXCLUDED.bond_type,
        board=EXCLUDED.board, currency=EXCLUDED.currency, face_value=EXCLUDED.face_value,
        coupon_percent=EXCLUDED.coupon_percent, coupon_value=EXCLUDED.coupon_value,
        coupon_period=EXCLUDED.coupon_period, maturity_date=EXCLUDED.maturity_date,
        offer_date=EXCLUDED.offer_date, has_amortization=EXCLUDED.has_amortization,
        lot_size=EXCLUDED.lot_size, listing_level=EXCLUDED.listing_level,
        last_price=EXCLUDED.last_price, ytm=EXCLUDED.ytm, duration_days=EXCLUDED.duration_days,
        accrued_int=EXCLUDED.accrued_int, coupon_type=EXCLUDED.coupon_type, ytm_kind=EXCLUDED.ytm_kind,
        is_defaulted=EXCLUDED.is_defaulted, risk_tier=EXCLUDED.risk_tier, spread_bp=EXCLUDED.spread_bp,
        agency_rating=EXCLUDED.agency_rating, agency_rating_source=EXCLUDED.agency_rating_source,
        updated_at=EXCLUDED.updated_at
""")


def upsert_bond(db: Session, rec: dict, curve: list,
                meta: dict | None = None, ratings: dict | None = None) -> None:
    s, m = rec["s"], rec["m"]
    meta = meta or {}
    ratings = ratings or {}
    ytm = _f(m.get("YIELD"))
    # YTM-артефакт: у бумаги на пороге оферты/погашения MOEX аннуализирует доходность
    # в абсурд (тысячи %). Это не доходность, а мусор — обнуляем (каскадом спред/тир
    # тоже None: «нет осмысленной рыночной оценки»). Заодно спасает от переполнения
    # числового поля. Реальные ВДО (до ~100-300%) сохраняем — их ловит yield_anomaly.
    if ytm is not None and (ytm > 300 or ytm < -100):
        ytm = None
    dur_days = int(m.get("DURATION")) if m.get("DURATION") not in (None, "", 0) else None
    dur_years = dur_days / 365 if dur_days else None

    # класс выпуска: муни/субфед видны только в глобальном type (торгуются на TQCB)
    bond_type = rec["bond_type"]
    if meta.get("glob_type") in _MUNI_TYPES:
        bond_type = "muni"

    # дефолт: режим Д (борд TQRD) или отметка дефолта в описании
    is_defaulted = rec["board"] == "TQRD" or bool(meta.get("defaulted"))

    spread_bp = None
    if bond_type != "ofz" and ytm is not None and dur_years:
        base = ofz_yield_at(curve, dur_years)
        if base is not None:
            spread_bp = round((ytm - base) * 100)   # п.п. → б.п.

    rating = ratings.get(s.get("ISIN"))
    issuer_name = meta.get("name") or s.get("EMITENT_TITLE")
    issuer_ticker = match_issuer_ticker(issuer_name or s.get("SHORTNAME"),
                                        allow_auto=(bond_type not in ("muni", "ofz")))
    db.execute(_UPSERT, {
        "secid": s["SECID"], "isin": s.get("ISIN"), "short_name": s.get("SHORTNAME") or s["SECID"],
        "issuer_name": issuer_name, "issuer_ticker": issuer_ticker, "bond_type": bond_type, "board": rec["board"],
        "currency": s.get("FACEUNIT"), "face_value": _f(s.get("FACEVALUE")),
        "coupon_percent": _f(s.get("COUPONPERCENT")), "coupon_value": _f(s.get("COUPONVALUE")),
        "coupon_period": int(s["COUPONPERIOD"]) if s.get("COUPONPERIOD") else None,
        "maturity_date": _d(s.get("MATDATE")), "offer_date": _d(s.get("OFFERDATE")),
        "has_amortization": False, "lot_size": int(s["LOTSIZE"]) if s.get("LOTSIZE") else None,
        "listing_level": int(s["LISTLEVEL"]) if s.get("LISTLEVEL") else None,
        "last_price": _f(m.get("LCURRENTPRICE") or m.get("LAST")), "ytm": ytm,
        "duration_days": dur_days, "accrued_int": _f(s.get("ACCRUEDINT")),
        "coupon_type": meta.get("coupon_type"), "ytm_kind": meta.get("ytm_kind"),
        "is_defaulted": is_defaulted,
        "risk_tier": classify_risk(bond_type, spread_bp), "spread_bp": spread_bp,
        "agency_rating": rating[0] if rating else None,
        "agency_rating_source": rating[1] if rating else None,
        "updated_at": datetime.now(timezone.utc),
    })


def fetch_cashflow(secid: str) -> dict:
    """Календарь купонов/амортизаций/оферт одной облигации (для блока денежного потока)."""
    data = _get(f"https://iss.moex.com/iss/securities/{secid}/bondization.json?iss.meta=off&limit=100")
    out = {"coupons": [], "amortizations": [], "offers": []}
    for block in ("coupons", "amortizations", "offers"):
        b = data.get(block)
        if not b:
            continue
        cols = b["columns"]
        out[block] = [dict(zip(cols, r)) for r in b["data"]]
    return out
