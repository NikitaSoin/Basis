"""Ингестор рейтинговых действий агентств АКРА и НКР → шина сигналов карточек.

Владелец (2026-07-28): «рейтинговые агентства — первыми» в контуре «входной
поток → дообновление карточек». Это САМОЕ ценное новое официальное сырьё по
облигациям: присвоение / подтверждение / повышение / понижение рейтинга,
изменение прогноза, дефолт — по КОНКРЕТНОМУ эмитенту. Наш агентский рейтинг
бонда (bonds.agency_rating) сейчас из smart-lab-среза и стареет; здесь берём
напрямую у источника.

Что берём и куда:
- АКРА (acra-ratings.ru/press-releases) и НКР (ratings.ru/ratings/press-releases)
  — обе отдают ЧИСТЫЙ серверный HTML (без JS-рендера), заголовок несёт всё:
  действие + эмитент + уровень + прогноз (+ ISIN у выпусков). Парсим список.
  НКР: дата и эмитент — в URL-slug (…-RA-DDMMYY/). АКРА: дату берём из релиза.
- Эксперт РА / НРА — отложены: рендерят релизы через JS (нужен headless).

Матчинг «действие → наша бумага» — два канала, разной строгости:
- ISIN-ТОЧНЫЙ (100%): ISIN из заголовка → Bond.isin. Обновляем官 agency_rating
  ЭТОГО выпуска напрямую (факт от источника > устаревший smart-lab). Жёсткое
  следствие (питает скринер) — только точный ISIN, без фаззи.
- ИМЯ ЭМИТЕНТА → Company (мягкое следствие): нормализованное имя == имя компании
  → CompanySignal (вкладка «Облигации»). Строгое равенство ядра имени, чтобы не
  повторить ложные срабатывания keyword-шины (см. observer-source-map §8).

Официальный источник → trust="official", internal=False (публичный сигнал).
Идемпотентность — через CompanySignal._upsert (dedup_key = URL релиза).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

import requests
import urllib3
from sqlalchemy.orm import Session

from app.models.bond import Bond
from app.models.company import Company
from app.services import company_signals

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_TIMEOUT = 25

_ACRA_LIST = "https://www.acra-ratings.ru/press-releases/?sort=date&order=desc"
_ACRA_BASE = "https://www.acra-ratings.ru"
_NKR_LIST = "https://ratings.ru/ratings/press-releases/"
_NKR_BASE = "https://ratings.ru"

# --- нормализация рейтинговых уровней ---
# Агентства мешают кириллицу и латиницу (АКРА «AА(RU)» = лат.A + кир.А). РФ-шкала
# ВСЕГДА несёт суффикс «(RU)» (АКРА) / «.ru» (НКР/Эксперт) — якоримся на него, а
# буквы уровня нормализуем ТОЧЕЧНО (translate по всему заголовку ломает русские
# слова-маркеры «УРОВНЕ»/«РЕЙТИНГ» в ЗАГЛАВНЫХ титулах АКРА: Р→P, Н→H).
_CYR2LAT = str.maketrans("АВСЕ", "ABCE")
_LEVEL_RE = r"(?:AAA|AA|A|BBB|BB|B|CCC|CC|C|D)(?:[+\-])?"  # для матчинга в тексте (латиница)
# токен рейтинга: 1–3 буквы уровня (лат/кир) + знак, ОБЯЗАТЕЛЬНО с РФ-суффиксом
_RATING_TOKEN = re.compile(r"([ABCDАВСЕ]{1,3}[+\-]?)\s*(?:\((?:RU|ru)\)|\.ru|\bru\b)")

_ACTION_RULES = [
    (r"снизил|понизил", "downgrade"),
    (r"повысил", "upgrade"),
    (r"установил статус|объявил дефолт|\bдефолт\b", "default"),
    (r"присвоил", "assigned"),
    (r"подтвердил", "affirmed"),
    (r"отозвал|прекратил", "withdrawn"),
    (r"изменил.{0,25}прогноз|прогноз.{0,25}(?:измен|пересмотр)", "outlook_change"),
]
_ACTION_RU = {
    "downgrade": "понизило рейтинг", "upgrade": "повысило рейтинг",
    "assigned": "присвоило рейтинг", "affirmed": "подтвердило рейтинг",
    "withdrawn": "отозвало рейтинг", "outlook_change": "изменило прогноз",
    "default": "зафиксировало дефолт",
}
# важность события для карточки
_IMPORTANCE = {
    "downgrade": "high", "default": "high", "upgrade": "high",
    "assigned": "medium", "withdrawn": "medium", "outlook_change": "medium",
    "affirmed": "low",
}

_OUTLOOK_RULES = [
    (r"стабильн", "стабильный"), (r"негативн", "негативный"),
    (r"позитивн", "позитивный"), (r"развивающ", "развивающийся"),
]
_OUTLOOK_WORDS = {"стабильный", "негативный", "позитивный", "развивающийся"}
_ISIN_RE = r"RU[0-9A-Z]{10}"

# слова-формы, которые вычищаем при нормализации имени эмитента
_ORG_FORMS = re.compile(
    r"\b(пао|ао|оао|зао|ооо|нпо|нко|нао|пко|ик|скб|гк|мкпао|мкао|"
    r"группа|холдинговая\s+компания|коммерческий\s+банк|"
    r"акционерн\w+\s+обществ\w+|банк)\b", re.IGNORECASE)


# ----------------------------- ПАРСИНГ -----------------------------
def _clean(raw: str) -> str:
    import html
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))).strip()


def _levels(title: str) -> list[str]:
    """Все РЕАЛЬНЫЕ уровни в порядке появления. Суффикс-якорь (RU)/.ru отсекает
    случайные буквы из слов/серий; буквы нормализуем точечно (кир→лат)."""
    return [m.group(1).upper().translate(_CYR2LAT) for m in _RATING_TOKEN.finditer(title)]


def _resulting_rating(title: str, action: str | None) -> str | None:
    # дефолт часто пишут «до D» / «статус D» / «в дефолт» БЕЗ суффикса шкалы —
    # проверяем это ПЕРВЫМ (иначе итоговым станет предыдущий уровень «с CC.ru»)
    if action in ("downgrade", "default") and re.search(
            r"\bдо\s+D\b|статус\s+«?D\b|\bв\s+дефолт", title, re.I):
        return "D"
    lv = _levels(title)
    if lv:
        # «с X до Y» / повышение-понижение → итоговый = последний; иначе первый
        if action in ("upgrade", "downgrade") or re.search(r"\bдо\s", title.lower()):
            return lv[-1]
        return lv[0]
    if re.search(r"\bдефолт\b", title, re.I):
        return "D"
    return None


def _outlook(title: str) -> str | None:
    low = title.lower()
    if "прогноз" not in low:
        return None
    tail = low[low.index("прогноз"):]
    for pat, code in _OUTLOOK_RULES:
        if re.search(pat, tail):
            return code
    return None


def _issuer_name(title: str) -> str | None:
    # 1) первое содержательное имя в кавычках (не слово-прогноз, не уровень)
    for q in re.findall(r"[«\"]([^»\"]{2,90})[»\"]", title):
        s = q.strip()
        if s.lower() in _OUTLOOK_WORDS:
            continue
        if re.fullmatch(_LEVEL_RE + r"(?:\.ru|\(RU\))?", s.translate(_CYR2LAT), re.I):
            continue
        return s
    # 2) регион (муниципальные выпуски) — без кавычек
    m = re.search(r"(РЕСПУБЛИК\w+\s+[А-ЯЁ][\w\-]+|[А-ЯЁ][\w\-]+\s+ОБЛАСТ\w+|"
                  r"[А-ЯЁ][\w\-]+\s+КРА[ЯЙ]|[А-ЯЁ][\w\-]+\s+АВТОНОМН\w+\s+ОКРУГ\w*)",
                  title, re.I)
    if m:
        return m.group(1).strip()
    # 3) ПАО/АО/ООО без кавычек: «ПАО МОСКОВСКАЯ БИРЖА»
    m = re.search(r"\b(?:ПАО|АО|ООО|ОАО|ЗАО|МКПАО)\s+([А-ЯЁ][А-ЯЁA-Z0-9 \-«»]{2,45}?)"
                  r"(?:\s+НА\s+УРОВНЕ|\s+С\s+|\s+ДО\s+|,|$)", title)
    if m:
        return re.sub(r"[«»]", "", m.group(1)).strip()
    return None


def _parse_title(title: str) -> dict:
    t = re.sub(r"^(?:АКРА|НКР)\s+", "", title).strip()
    low = t.lower()
    action = None
    for pat, code in _ACTION_RULES:
        if re.search(pat, low):
            action = code
            break
    return {
        "action": action,
        "rating": _resulting_rating(t, action),
        "outlook": _outlook(t),
        "isins": re.findall(_ISIN_RE, t.translate(_CYR2LAT)),
        "issuer": _issuer_name(t),
        "title": title.strip(),
    }


# ----------------------------- ДОБЫЧА -----------------------------
def _get(url: str) -> str | None:
    """GET с фолбэком по TLS: АКРА/НКР на РОССИЙСКОМ нац. CA (Минцифры), которого
    нет в mozilla/certifi-бандле → при SSLError повторяем без верификации цепочки.
    Читаем ПУБЛИЧНЫЕ пресс-релизы, секретов не передаём — фолбэк безопасен.
    (На боевом Timeweb-сервере системный бандл обычно содержит нац. CA — тогда
    сработает первая, верифицированная попытка.)"""
    hdr = {"User-Agent": _UA}
    for verify in (True, False):
        try:
            r = requests.get(url, headers=hdr, timeout=_TIMEOUT, verify=verify)
            if r.status_code == 200:
                return r.text
            logger.warning("rating_agencies: %s → HTTP %s", url, r.status_code)
            return None
        except requests.exceptions.SSLError:
            continue  # пробуем verify=False
        except Exception as e:  # noqa: BLE001
            logger.warning("rating_agencies: %s недоступен (%s)", url, e)
            return None
    return None


def _acra_detail_date(rel_url: str) -> date | None:
    html_txt = _get(_ACRA_BASE + rel_url)
    if not html_txt:
        return None
    m = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", html_txt)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def fetch_acra(limit: int = 15, fetch_dates: bool = True) -> list[dict]:
    html_txt = _get(_ACRA_LIST)
    if not html_txt:
        return []
    out, seen = [], set()
    for rel, raw in re.findall(
            r'<a[^>]+href="(/press-releases/\d+/)"[^>]*>(.*?)</a>', html_txt, re.S):
        if rel in seen:
            continue
        seen.add(rel)
        title = _clean(raw)
        if not title or len(title) < 15:
            continue
        p = _parse_title(title)
        p["url"] = _ACRA_BASE + rel
        p["agency"] = "АКРА"
        p["agency_key"] = "acra"
        p["date"] = _acra_detail_date(rel) if fetch_dates else None
        out.append(p)
        if len(out) >= limit:
            break
    return out


def fetch_nkr(limit: int = 25) -> list[dict]:
    html_txt = _get(_NKR_LIST)
    if not html_txt:
        return []
    out, seen = [], set()
    for rel, raw in re.findall(
            r'<a[^>]+href="(/ratings/press-releases/[^"]+/)"[^>]*>(.*?)</a>', html_txt, re.S):
        if rel in seen:
            continue
        seen.add(rel)
        title = _clean(raw)
        if not title or "рейтинг" not in title.lower():
            continue
        p = _parse_title(title)
        p["url"] = _NKR_BASE + rel
        p["agency"] = "НКР"
        p["agency_key"] = "nkr"
        md = re.search(r"-(\d{2})(\d{2})(\d{2})/$", rel)
        p["date"] = None
        if md:
            try:
                p["date"] = date(2000 + int(md.group(3)), int(md.group(2)), int(md.group(1)))
            except ValueError:
                pass
        out.append(p)
        if len(out) >= limit:
            break
    return out


# ----------------------------- МАТЧИНГ -----------------------------
def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"'`]", " ", s)
    s = _ORG_FORMS.sub(" ", s)
    s = re.sub(r"[^\w\s\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _company_index(db: Session) -> dict[str, str]:
    idx: dict[str, str] = {}
    for c in db.query(Company).all():
        n = _norm(c.name)
        if n and n not in idx:
            idx[n] = c.ticker
    return idx


def _match(db: Session, action: dict, comp_idx: dict[str, str]) -> tuple[set[str], list[Bond]]:
    """→ (тикеры для сигналов карточек, конкретные бонды для обновления рейтинга).

    Три канала:
      • ISIN-точный (выпуск → бумага → эмитент) — самый надёжный;
      • имя эмитента → Company (строгое равенство ядра) — сигнал карточки;
      • имя эмитента → префикс имени бонда — для эмитентов-облигаций БЕЗ карточки
        компании (обновляем их agency_rating; сигнала карточки не будет — не к чему
        крепить, но официальный рейтинг в скринере/на странице бумаги освежается).
    """
    tickers: set[str] = set()
    bonds: list[Bond] = []
    seen_secids: set[str] = set()

    def _add_bond(b: Bond) -> None:
        if b.secid not in seen_secids:
            seen_secids.add(b.secid)
            bonds.append(b)
            if b.issuer_ticker:
                tickers.add(b.issuer_ticker)

    # 1) ISIN-точный
    for isin in action.get("isins", []):
        b = db.query(Bond).filter(Bond.isin == isin).first()
        if b:
            _add_bond(b)

    issuer = (action.get("issuer") or "").strip()
    ni = _norm(issuer)
    if ni and len(ni) >= 3:
        # 2) Company (строгое)
        if ni in comp_idx:
            tickers.add(comp_idx[ni])
        else:
            for cname, tk in comp_idx.items():
                if len(cname) >= 5 and (ni == cname or ni.startswith(cname + " ")
                                        or cname.startswith(ni + " ")):
                    tickers.add(tk)
                    break
        # 3) бонды по префиксу имени эмитента (эмитенты-облигации без карточки).
        #    ТОЛЬКО для issuer-level релизов (без ISIN): релиз с ISIN — про КОНКРЕТНУЮ
        #    серию, сёстринские выпуски могут иметь иной рейтинг — их не трогаем.
        if (len(issuer) >= 4 and not action.get("isins")
                and not re.search(r"област|республик|кра[йя]|округ", ni)):
            more = (db.query(Bond)
                    .filter(Bond.issuer_name.ilike(f"{issuer}%")).limit(60).all())
            if len(more) <= 40:  # защита от слишком широкого совпадения
                for b in more:
                    _add_bond(b)
    return tickers, bonds


# ----------------------------- ЗАПИСЬ -----------------------------
def _signal_text(action: dict) -> tuple[str, str]:
    a = action.get("action")
    verb = _ACTION_RU.get(a, "рейтинговое действие")
    rating = action.get("rating")
    outlook = action.get("outlook")
    head = f"{action['agency']} {verb}"
    if rating and a not in ("withdrawn", "outlook_change"):
        head += f" — {rating}"
    if outlook:
        head += f", прогноз {outlook}"
    return head[:400], action.get("title", "")[:1000]


def _update_bond_rating(bond: Bond, action: dict) -> bool:
    """Точечно освежаем официальный рейтинг бумаги от первоисточника.
    Только при конкретном уровне и «настоящем» действии (не отзыв/прогноз)."""
    a = action.get("action")
    rating = action.get("rating")
    if a in ("withdrawn", "outlook_change") or not rating:
        return False
    src = f"{action['agency']} ({action['date'].isoformat()})" if action.get("date") else action["agency"]
    if bond.agency_rating == rating and (bond.agency_rating_source or "").startswith(action["agency"]):
        return False
    bond.agency_rating = rating
    bond.agency_rating_source = src[:32]
    return True


def refresh(db: Session, acra_limit: int = 15, nkr_limit: int = 25,
            acra_dates: bool = False) -> dict:
    """Полный прогон ингестора. acra_dates=False (по умолчанию для крона):
    НЕ ходить в каждый релиз АКРА за точной датой (~10с/релиз, АКРА медленная) —
    ставим дату прогона; дедуп всё равно по URL, а точная дата в одном клике на
    источнике. acra_dates=True — для разового бэкфилла с точными датами."""
    actions = fetch_acra(limit=acra_limit, fetch_dates=acra_dates) + fetch_nkr(limit=nkr_limit)
    comp_idx = _company_index(db)
    stats = {"fetched": len(actions), "signals": 0, "bonds_updated": 0, "matched_actions": 0}
    for act in actions:
        if not act.get("action"):
            continue
        tickers, bonds = _match(db, act, comp_idx)
        if not tickers and not bonds:
            continue
        stats["matched_actions"] += 1
        title, summary = _signal_text(act)
        imp = _IMPORTANCE.get(act["action"], "medium")
        pub = act.get("date") or date.today()
        dedup = (act.get("url") or f"{act['agency']}:{act.get('issuer')}")[:64]
        for tk in tickers:
            if company_signals._upsert(
                    db, ticker=tk, signal_type="rating_action", card_tab="bonds",
                    importance=imp, trust="official", internal=False,
                    title=title, summary=summary, source_key=act.get("agency_key", "rating"),
                    source_url=act.get("url"), published_at=pub, dedup_key=dedup):
                stats["signals"] += 1
        # обновление официального рейтинга бумаги — только ISIN-точное
        touched = False
        for b in bonds:
            if _update_bond_rating(b, act):
                touched = True
                stats["bonds_updated"] += 1
        if touched:
            try:
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
    logger.info("rating_agencies.refresh: %s", stats)
    return stats
