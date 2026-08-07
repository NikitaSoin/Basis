"""Отраслевой барометр — «в каком состоянии сейчас каждый сектор рынка РФ».

Владелец (2026-08-07): «в бизнесе надо сделать оценку текущей ситуации, где
будет говориться, а в каком состоянии сейчас банковский сектор, нефтегаз,
металлургия (чёрная и цветная) и все остальные, и сделать как у
макроэкономики / геополитики / институтов».

🔴 ПОЧЕМУ БАРОМЕТР НЕ МОЖЕТ СТОЯТЬ НА ЦЕНАХ ТОВАРОВ.
Первым делом хочется собрать его из товарных рядов — они у нас живые и
ежедневные. Но проверка показала: ценовой ряд есть только у 4 секторов из 13
(металлургия 18 компаний из 30, нефтегаз 16 из 23, химия 4 из 10, потребительский
1 из 22). Для энергетики, машиностроения, IT, телекома, транспорта, девелопмента,
здравоохранения живой цены их рынка у нас нет ВООБЩЕ. Барометр «по ценам» молча
выродился бы в «четыре сектора с оценкой и девять пустых» — то есть в ту самую
болезнь, когда отсутствие данных выглядит как отсутствие проблемы.
Поэтому опора — ОТЧЁТНОСТЬ КОМПАНИЙ СЕКТОРА (есть по всем 13, 239 разборов),
макро-рамка (ставка/инфляция/курс бьют по всем) и лента; товарные цены идут
дополнительным входом там, где они есть.

🔴 ЧЁРНАЯ И ЦВЕТНАЯ МЕТАЛЛУРГИЯ РАЗДЕЛЕНЫ. Владелец назвал это прямо, и он прав
по существу: у стали драйвер — внутренний спрос и ставка (стройка,
машиностроение), у золота и цветных — мировая цена и курс. В одном барометре их
средняя не значит ничего. По той же причине IT и телеком идут вместе (общий
регулятор и рынок), а машиностроение отделено от металлургии.

Темп — НЕДЕЛЬНЫЙ, как у портретов очага и институтов: отраслевой цикл не
разворачивается за сутки, ежедневная перегенерация давала бы шум.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.models.geo_digest import GeoDigestArticle
from app.services import llm
from app.services.institutions_profile import _blocklist_hit, _sanitize_sources

# 🔴 Свой детектор имён, а не общий из institutions_profile. Тот ловит шаблон
# «Слово в ВС/ЦБ/ГП» — для институционального текста это оправдано («Краснов в
# ВС»), но в отраслевом обороты вроде «ставки в ЦБ», «размещения в ЦБ»,
# «поставки в ВС» законны и встречаются постоянно. Первый же прогон батча был
# отклонён целиком именно на этом, хотя фамилий в тексте не было.
# Здесь ищем узко: инициал с точкой перед фамилией («А. Петров») либо
# «глава/председатель/министр <Фамилия>» — то, что действительно является
# указанием на человека, а не совпадением предлога.
# 🔴 Шаблон пришлось ужесточить ДВАЖДЫ. Первая версия ловила «Слово в ЦБ» и
# резала законное «ставки в ЦБ». Вторая («А. Петров») отклонила целый батч на
# названии компании «М.Видео»: точка без пробела между заглавной буквой и словом
# с большой буквы выглядит как инициал. Теперь требуем ПРОБЕЛ после точки И
# фамильное окончание — «М.Видео» проходит, «А. Петров» нет.
_PERSON_SECTOR = __import__("re").compile(
    r"\b[А-ЯЁ]\.\s[А-ЯЁ][а-яё]{2,}(?:ов|ев|ин|ко|ук|ян|ский|цкий)\b"
    r"|\b(?:глав[аеуы]|председател\w+|министр\w*|гендиректор\w*|президент)\s+"
    r"[А-ЯЁ][а-яё]{3,}(?:ов|ев|ин|ко|ук|ян)\b")

logger = logging.getLogger(__name__)

_KIND = "secbaro"          # varchar(8), см. пояснение в geo_conflict_profile
_WINDOW_DAYS = 45
_MIN_INPUTS = 2

# Отраслевые группы витрины. Ключ — стабильный id (по нему сравниваем с прошлым
# замером), db_sectors — значения companies.sector, из которых собираем компании.
# Группы НЕ равны значениям в БД намеренно: металлургия разделена на чёрную и
# цветную (разные драйверы), IT и телеком объединены (общий рынок и регулятор).
SECTORS = [
    {"key": "banks", "label": "Банки и финансы", "db_sectors": ["Финансы"],
     "drivers": "ключевая ставка и процентная маржа, качество кредитного портфеля, "
                "спрос на кредит, регуляторные требования к капиталу"},
    {"key": "oil_gas", "label": "Нефть и газ", "db_sectors": ["Нефть и газ"],
     "drivers": "цена Urals и дисконт к Brent, курс рубля, налоги (НДПИ, демпфер), "
                "экспортные маршруты и санкционные ограничения"},
    {"key": "steel", "label": "Чёрная металлургия и уголь", "db_sectors": ["Металлургия"],
     "only_tickers": ["CHMF", "NLMK", "MAGN", "MTLR", "MTLRP", "RASP", "TRMK", "CHMK",
                      "AMEZ", "IGST", "IGSTP", "KOGK", "UKUZ", "BLNG", "PRFN"],
     "drivers": "внутренний спрос на прокат (стройка, машиностроение), ключевая ставка "
                "как ограничитель этого спроса, экспортные цены и пошлины, цены на уголь"},
    {"key": "nonferrous", "label": "Цветная металлургия и драгметаллы", "db_sectors": ["Металлургия"],
     "only_tickers": ["GMKN", "RUAL", "ENPG", "PLZL", "SELG", "UGLD", "ALRS", "VSMO",
                      "ROLO", "LNZL", "LNZLP", "BRZL", "MGNZ", "UNKL", "SGZH"],
     "drivers": "мировые цены металлов и курс рубля (экспортная выручка), спрос "
                "мировой промышленности, санкционные ограничения на сбыт"},
    {"key": "power", "label": "Электроэнергетика", "db_sectors": ["Электроэнергетика"],
     "drivers": "тарифы и их индексация, потребление электроэнергии, платежи за "
                "мощность, инвестпрограммы и их окупаемость"},
    {"key": "chem", "label": "Химия и удобрения", "db_sectors": ["Химия"],
     "drivers": "мировые цены удобрений, курс рубля, цена газа как сырья, "
                "экспортные пошлины и логистика"},
    {"key": "consumer", "label": "Потребительский сектор", "db_sectors": ["Потребительский сектор"],
     "drivers": "реальные доходы и потребительский спрос, продовольственная инфляция, "
                "конкуренция сетей и маркетплейсов"},
    {"key": "it_telecom", "label": "IT и телеком", "db_sectors": ["IT-сектор", "Телеком"],
     "drivers": "спрос на импортозамещение и госзаказ, налоговые льготы для IT, "
                "капзатраты на исполнение регуляторных требований, стоимость денег"},
    {"key": "transport", "label": "Транспорт и логистика", "db_sectors": ["Транспорт и логистика"],
     "drivers": "грузопоток и ставки фрахта, тарифы естественных монополий, "
                "санкционные ограничения на маршруты, пассажиропоток"},
    {"key": "realty", "label": "Девелопмент", "db_sectors": ["Девелопмент"],
     "drivers": "ипотечные ставки и льготные программы, распроданность и эскроу, "
                "себестоимость строительства, спрос на жильё"},
    {"key": "machinery", "label": "Машиностроение", "db_sectors": ["Машиностроение"],
     "drivers": "госзаказ и программы поддержки спроса, локализация, спрос на "
                "транспорт и оборудование, стоимость финансирования"},
    {"key": "health", "label": "Здравоохранение и фарма", "db_sectors": ["Здравоохранение"],
     "drivers": "тарифы ОМС и госзакупки, регулирование цен на жизненно важные "
                "препараты, спрос на платную медицину, локализация производства"},
]

# Батчи: секторы внутри одного прогона должны быть СВЯЗАНЫ (общие драйверы),
# тогда модель видит перетоки — «ставка душит стройку, стройка тянет вниз сталь».
_BATCHES = [
    ("ставка и внутренний спрос", ["banks", "realty", "consumer"]),
    ("экспортное сырьё", ["oil_gas", "nonferrous", "chem"]),
    ("внутренняя промышленность", ["steel", "machinery", "power"]),
    ("услуги и инфраструктура", ["it_telecom", "transport", "health"]),
]

_SPEC = """

================================================================
ФОРМАТ ОТВЕТА — СТРОГО JSON, на русском, без текста вне JSON:

{"sectors": [
  {"key": "<ключ сектора, дословно как дан>",
   "score": <1..5, шаг 0.5: 1 — отрасль в кризисе (спрос падает, маржа сжимается,
             компании режут инвестиции), 3 — обычное состояние, 5 — подъём
             (спрос растёт, маржа расширяется)>,
   "direction": "<ухудшение|без изменений|улучшение>",
   "headline": "<ОДНА фраза: что происходит в отрасли сейчас>",
   "what_happens": "<2-3 предложения простым языком: что с спросом, ценами,
     издержками и прибылью отрасли. Конкретно, со ссылкой на то, что видно в
     переданных данных>",
   "for_investor": "<1-2 фразы: что это значит для того, кто держит акции этой
     отрасли — через выручку, маржу, дивиденды, оценку>",
   "winners": "<кто внутри отрасли в лучшем положении и ПОЧЕМУ — тип компаний
     или конкретные тикеры из переданного списка>",
   "losers": "<кто в худшем и почему>",
   "watch": "<1 наблюдаемое событие, которое изменит картину>",
   "confidence": "<низкая|средняя|высокая>"}
]}

ПРАВИЛА:
• score — СОСТОЯНИЕ отрасли, direction — КУДА движется. Можно иметь низкий балл
  и «без изменений» (давно на дне), можно высокий и «ухудшение» (пик пройден).
• Двигай балл относительно прошлого замера ТОЛЬКО если в данных есть основание.
  Нет основания — сохрани прошлый балл. Отраслевой цикл не разворачивается за
  неделю; шевеление балла в тишине обесценивает замер.
• Опирайся на ПЕРЕДАННЫЕ данные: отчётность компаний, цены, макро-рамку, ленту.
  Не выдумывай долей рынка, объёмов и темпов, которых в данных нет.
• confidence «низкая», если по отрасли почти ничего не передано — это честнее
  уверенного балла из воздуха.
• Тикеры в winners/losers бери ТОЛЬКО из переданного списка компаний отрасли.
• Никаких рекомендаций «покупать/продавать» и целевых цен. Никаких фамилий.
• Пиши коротко: каждое поле — одна-две фразы, не абзац.
"""


def _macro_frame(db: Session) -> str:
    """Общая рамка: то, что бьёт по всем отраслям сразу."""
    rows = db.execute(text("""
        SELECT i.code, i.title, p.value, p.as_of
        FROM macro_indicators i
        JOIN LATERAL (SELECT value, as_of FROM macro_data_points
                      WHERE indicator_code = i.code AND metric = 'level'
                      ORDER BY as_of DESC LIMIT 1) p ON TRUE
        WHERE i.code IN ('key_rate','inflation','usdrub','cnyrub','unemployment',
                         'nominal_wage','ppi','credit_economy')
    """)).fetchall()
    if not rows:
        return ""
    parts = [f"  {r[1]}: {r[2]} (на {r[3]})" for r in rows]
    return "МАКРО-РАМКА (действует на все отрасли):\n" + "\n".join(parts)


def _sector_tickers(db: Session, sec: dict) -> list[str]:
    only = sec.get("only_tickers")
    if only:
        rows = db.execute(text("SELECT ticker FROM companies WHERE ticker = ANY(:t)"),
                          {"t": only}).fetchall()
    else:
        rows = db.execute(text("SELECT ticker FROM companies WHERE sector = ANY(:s)"),
                          {"s": sec["db_sectors"]}).fetchall()
    return sorted(r[0] for r in rows)


def _sector_earnings(db: Session, tickers: list[str], days: int = 120) -> list[str]:
    """Свежая отчётность компаний отрасли — главный вход барометра: она есть по
    всем 13 секторам, в отличие от товарных цен."""
    if not tickers:
        return []
    rows = db.execute(text("""
        SELECT e.ticker, e.period, e.standard, e.published_at, d.one_liner, d.headline
        FROM earnings_reports e
        LEFT JOIN earnings_digests d ON d.report_id = e.id
        WHERE e.ticker = ANY(:t) AND e.status = 'processed'
          AND e.published_at > current_date - :d
        ORDER BY e.published_at DESC LIMIT 14
    """), {"t": tickers, "d": days}).fetchall()
    out = []
    for r in rows:
        txt = (r[4] or r[5] or "").strip()
        out.append(f"  {r[0]} · {r[1] or ''} {r[2] or ''} (опубл. {r[3]}): {txt[:220]}")
    return out


def _sector_prices(db: Session, tickers: list[str]) -> list[str]:
    """Товарные ряды компаний отрасли, если есть: цена сейчас и дельта за квартал."""
    import glob
    import os
    keys: set[str] = set()
    for t in tickers:
        p = f"companies/{t}/market.json"
        if not os.path.exists(p):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for x in ((d.get("commodity_exposure") or {}).get("revenue_commodities") or []):
            k = x.get("benchmark_key") or ""
            if k.startswith("macro:"):
                keys.add(k[6:])
    if not keys:
        return []
    out = []
    for k in sorted(keys):
        rows = db.execute(text("""
            SELECT value, as_of FROM macro_data_points
            WHERE indicator_code = :k AND metric = 'level'
            ORDER BY as_of DESC LIMIT 90
        """), {"k": k}).fetchall()
        if not rows:
            continue
        cur, cur_d = float(rows[0][0]), rows[0][1]
        old = float(rows[-1][0]) if len(rows) > 1 else cur
        delta = ((cur - old) / old * 100) if old else 0.0
        title = db.execute(text("SELECT title FROM macro_indicators WHERE code = :k"),
                           {"k": k}).scalar() or k
        out.append(f"  {title}: {cur:g} (на {cur_d}), изменение за период {delta:+.1f}%")
    return out


def _sector_articles(db: Session, label: str, drivers: str, limit: int = 6) -> list[str]:
    """Материалы ленты. Отбор грубый — по совпадению слов из названия и драйверов:
    точной привязки статьи к отрасли у нас нет, а гонять LLM-классификатор ради
    подбора контекста дороже, чем отдать модели чуть более широкий набор."""
    words = [w.lower() for w in (label + " " + drivers).replace(",", " ").split()
             if len(w) > 5][:12]
    if not words:
        return []
    cutoff = date.today() - timedelta(days=_WINDOW_DAYS)
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(("business", "macro")),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(60).all())
    hits = []
    for r in rows:
        blob = f"{r.title} {r.summary or ''}".lower()
        if any(w[:6] in blob for w in words):
            hits.append(f"  {r.published_at} {r.title}: {(r.summary or '')[:200]}")
        if len(hits) >= limit:
            break
    return hits


# Отраслевые ряды из sector_data_sync — какой код какой отрасли принадлежит.
# Явная таблица, а не префикс: связь «показатель → отрасль» должна быть видимой,
# иначе новый ряд молча не попадёт ни в один барометр.
_SECTOR_INDICATORS = {
    "power": ["sec_power_consumption", "sec_power_capacity"],
    "realty": ["sec_realty_construction", "sec_realty_top1_share"],
    "oil_gas": ["sec_urals_tax"],
    # Ставка по вкладам — стоимость фондирования банков, вторая половина
    # процентной маржи. Ключевая ставка у нас была, а по чём банки реально
    # привлекают деньги — нет; в реестре финансов это отмечено как «маржа не
    # питается ничем».
    "banks": ["sec_banks_deposit_rate"],
    "transport": ["sec_ports_turnover"],
    "it_telecom": ["sec_it_software_registry"],
}


def _sector_indicators(db: Session, sector_key: str) -> list[str]:
    codes = _SECTOR_INDICATORS.get(sector_key) or []
    if not codes:
        return []
    rows = db.execute(text("""
        SELECT i.title, p.value, p.as_of, i.unit
        FROM macro_indicators i
        JOIN LATERAL (SELECT value, as_of FROM macro_data_points
                      WHERE indicator_code = i.code AND metric = 'level'
                      ORDER BY as_of DESC LIMIT 1) p ON TRUE
        WHERE i.code = ANY(:c)
    """), {"c": codes}).fetchall()
    return [f"  {r[0]}: {r[1]:g} {r[3] or ''} (на {r[2]})" for r in rows]


def previous(db: Session) -> dict:
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == _KIND, BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    return (row.payload or {}) if row else {}


def _check(items: list[dict], allowed: set[str]) -> tuple[list[str], list[str]]:
    bad, notes = [], []
    for s in items:
        k = s.get("key")
        if not isinstance(s.get("score"), (int, float)):
            bad.append(f"{k}: балл не число")
        elif not (1 <= float(s["score"]) <= 5):
            bad.append(f"{k}: балл вне 1-5 ({s['score']})")
        if not s.get("headline"):
            bad.append(f"{k}: нет вердикта")
        if not s.get("for_investor"):
            notes.append(f"{k}: не сказано, что это значит инвестору")
    blob = json.dumps(items, ensure_ascii=False)
    m_p = _PERSON_SECTOR.search(blob)
    if m_p:
        bad.append(f"похоже на имя должностного лица: «{m_p.group(0)}»")
    m = _blocklist_hit(blob)
    if m:
        bad.append(f"блоклист: «{m.group(0)}»")
    return bad, notes


def _run_batch(db: Session, name: str, keys: list[str], macro: str,
               prev_map: dict) -> tuple[list[dict], list[str]]:
    secs = [s for s in SECTORS if s["key"] in keys]
    blocks, allowed = [], set()
    for sec in secs:
        tickers = _sector_tickers(db, sec)
        allowed.update(tickers)
        earn = _sector_earnings(db, tickers)
        prices = _sector_prices(db, tickers)
        arts = _sector_articles(db, sec["label"], sec["drivers"])
        b = [f"### ОТРАСЛЬ «{sec['label']}» (ключ {sec['key']})",
             f"Что определяет её экономику: {sec['drivers']}",
             f"Компании ({len(tickers)}): {', '.join(tickers[:40])}"]
        if prices:
            b.append("Цены на продукцию отрасли:\n" + "\n".join(prices))
        # Отраслевые показатели, собранные парсерами из источников реестра
        # (потребление электроэнергии, объём стройки и т.п.). Для девяти
        # секторов из тринадцати это ЕДИНСТВЕННЫЕ данные об их рынке — цен
        # на продукцию у них нет вовсе.
        ind = _sector_indicators(db, sec["key"])
        if ind:
            b.append("Показатели отрасли:\n" + "\n".join(ind))
        if earn:
            b.append("Свежая отчётность компаний отрасли:\n" + "\n".join(earn))
        else:
            b.append("Свежей отчётности по отрасли в базе нет — это повод для "
                     "низкой уверенности, а не для догадок.")
        if arts:
            b.append("Материалы ленты:\n" + "\n".join(arts))
        blocks.append("\n".join(b))
        if not earn and not prices:
            pass  # честно уйдёт в confidence=низкая

    prev_part = ""
    if prev_map:
        sub = {k: prev_map[k] for k in keys if k in prev_map}
        if sub:
            prev_part = ("\n\nПРОШЛЫЙ ЗАМЕР по этим отраслям (отправная точка):\n"
                         + json.dumps(sub, ensure_ascii=False, indent=1)[:6000])

    system = (
        "Ты — отраслевой аналитик Basis (независимая аналитика для частного "
        "инвестора в РФ). Ты оцениваешь СОСТОЯНИЕ ОТРАСЛЕЙ российского рынка: где "
        "отрасль сейчас, куда движется и что это значит для того, кто держит её "
        "акции. Пиши простым языком, без академических терминов и без жаргона.\n\n"
        + _SPEC
    )
    user = (f"БАТЧ «{name}». Оцени каждую отрасль ниже.\n\n{macro}\n\n"
            + "\n\n".join(blocks) + prev_part
            + f"\n\nСЕГОДНЯ: {date.today().isoformat()}")

    try:
        out = llm.complete(system, user, json_mode=True, thinking=True,
                           model=llm.pro_model(), max_tokens=7000, temperature=0.3)
    except llm.LLMError as e:
        return [], [f"батч «{name}»: LLM недоступен ({e})"]

    items = (out or {}).get("sectors") if isinstance(out, dict) else None
    if not isinstance(items, list) or not items:
        return [], [f"батч «{name}»: пустой ответ"]
    items = [s for s in items if isinstance(s, dict) and s.get("key") in keys]
    bad, notes = _check(items, allowed)
    if bad:
        return [], [f"батч «{name}» отклонён: {b}" for b in bad] + notes
    return items, [f"батч «{name}»: {n}" for n in notes]


def rebuild(db: Session) -> BarometerVersion | None:
    macro = _macro_frame(db)
    prev = previous(db)
    prev_map = {s["key"]: s for s in (prev.get("sectors") or [])}

    collected: list[dict] = []
    notes: list[str] = []
    for name, keys in _BATCHES:
        items, n = _run_batch(db, name, keys, macro, prev_map)
        notes.extend(n)
        if items:
            collected.extend(items)
        else:
            carried = [prev_map[k] for k in keys if k in prev_map]
            collected.extend(carried)
            if carried:
                notes.append(f"батч «{name}»: перенесены прошлые оценки")

    if len(collected) < _MIN_INPUTS:
        logger.warning("sector_barometer: собрано слишком мало отраслей (%d)", len(collected))
        return None

    labels = {s["key"]: s["label"] for s in SECTORS}
    for s in collected:
        s["label"] = labels.get(s.get("key"), s.get("key"))

    changes = []
    for s in collected:
        old = prev_map.get(s.get("key"))
        if old and isinstance(old.get("score"), (int, float)) and isinstance(s.get("score"), (int, float)):
            d = round(float(s["score"]) - float(old["score"]), 1)
            if abs(d) >= 0.5:
                changes.append({"key": s["key"], "label": s["label"],
                                "from": old["score"], "to": s["score"], "delta": d,
                                "why": s.get("headline")})

    payload = {
        "as_of": date.today().isoformat(),
        "sectors": sorted(collected, key=lambda x: -(x.get("score") or 0)),
        "changes": changes,
        # компактная сводка для соседних доменов и карточек компаний
        "for_agents": {s["key"]: {"score": s.get("score"), "direction": s.get("direction")}
                       for s in collected},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = _sanitize_sources(payload)

    row = BarometerVersion(kind=_KIND, source="auto", status="published",
                           payload=payload, gate_notes=notes[:20],
                           trigger_reason="еженедельный отраслевой барометр",
                           model_used=llm.pro_model())
    db.add(row); db.commit(); db.refresh(row)
    logger.info("sector_barometer: версия %s, отраслей %d, изменений %d",
                row.id, len(collected), len(changes))
    return row


def get_latest(db: Session) -> dict:
    return previous(db)


def for_agents(db: Session) -> dict:
    """Стабильный контракт для соседей (карточки компаний, макро, витрина)."""
    p = previous(db)
    if not p:
        return {}
    return {"as_of": p.get("as_of"), "sectors": p.get("for_agents") or {},
            "changes": [{"label": c.get("label"), "delta": c.get("delta")}
                        for c in (p.get("changes") or [])]}
