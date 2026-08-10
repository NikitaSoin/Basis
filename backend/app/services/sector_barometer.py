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
import re
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
   "market_numbers": "<ЦИФРЫ РЫНКА одной строкой: объёмы и цены с динамикой —
     «добыча 516 млн т (−2,8% г/г), Urals $75/барр (+29% г/г)». ТОЛЬКО из
     переданных данных; нет цифр — пустая строка, не выдумывай>",
   "deals": "<крупные сделки, слияния, вводы мощностей, уходы игроков, новые
     правила — то, что МЕНЯЕТ расстановку в отрасли. Из ленты и отчётности.
     Нет таких событий — пустая строка>",
   "env_link": "<связка со средой ОДНОЙ фразой и ТОЛЬКО если это правда важно для
     отрасли: как макро/геополитика/институты меняют её картину. Если переданные
     флаги соседних доменов противоречат твоей оценке — скажи об этом прямо.
     Нечего сказать — пустая строка, дежурных фраз не надо>",
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
• market_numbers и deals — это ФАКТЫ из переданного, а не пересказ вывода. Пусто
  лучше, чем общие слова: пустое поле честно показывает, что данных нет.
• env_link — не обязательное поле, но если по отрасли передан ОТРАСЛЕВОЙ ФЛАГ
  геополитики или замер институтов, связка ОБЯЗАНА называть конкретный механизм
  оттуда, а не общие слова. «Удары по НПЗ вывели около четверти переработки —
  downstream теряет объёмы и получает дорогие ремонты» — связка. «Геополитическая
  напряжённость поддерживает риск-премию в нефти» и «высокая ставка давит на
  оценку» — трюизмы, они не принимаются: ставка и так в макро-рамке.
• Про НАШИ ЧИСЛА: если пересказ в ленте противоречит блоку «НАШИ ЧИСЛА» — верь
  нашим числам и не пиши обратное. Назвать прибыльную компанию убыточной —
  ложный факт о бумаге, замер с таким полем целиком бракуется.
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


def _env_frame(db: Session) -> str:
    """Состояние СОСЕДНИХ доменов: гео, институты. Чтобы отраслевой вердикт не
    противоречил тому, что платформа говорит рядом.

    🔴 Зачем (владелец, 2026-08-09): «нужна связка бизнеса с макроэкономикой,
    геополитикой и институтами, чтобы не было противоречий между ними». Раньше
    барометр видел только макро-рамку и свои данные — и мог написать «спрос
    восстанавливается» в отрасли, по которой гео-барометр в тот же день держит
    флаг «негатив: четверть мощностей выведена ударами».

    Гео отдаёт ГОТОВЫЕ отраслевые флаги (`sector_flags`) — их и берём: это прямая
    связка, а не пересказ общей картины. Институты — баллы направлений (защита
    собственности, суды, госдоля), они бьют по отраслям через издержки и риск.
    """
    parts: list[str] = []
    try:
        from app.services.barometer_store import get_payload_with_meta
        geo = get_payload_with_meta(db, "geo") or {}
        if geo.get("summary"):
            parts.append("ГЕОПОЛИТИКА (оценка Обозревателя): "
                         + str(geo["summary"])[:400])
        flags = geo.get("sector_flags") or []
        if flags:
            parts.append("Отраслевые флаги геополитики — НЕ ПРОТИВОРЕЧЬ им, "
                         "а если твои данные говорят иначе, скажи об этом прямо:")
            for f in flags[:8]:
                parts.append(f"  {f.get('sector')}: {f.get('direction')} — "
                             f"{str(f.get('reasoning') or '')[:150]}")
    except Exception as e:  # noqa: BLE001 — соседний домен не должен ронять барометр
        logger.warning("sector_barometer: гео-контекст недоступен (%s)", type(e).__name__)
    try:
        from app.services.institutions_domains import for_agents as inst_agents
        inst = inst_agents(db) or {}
        doms = inst.get("domains") or {}
        if doms:
            titles = {"property": "защита собственности", "courts": "суды",
                      "state_share": "доля государства", "monopoly": "монополизация",
                      "competition": "конкуренция", "business_state": "конфликты бизнеса и государства"}
            row = [f"{titles[k]} {v.get('score')}/5 ({v.get('direction')})"
                   for k, v in doms.items() if k in titles]
            if row:
                parts.append(f"ИНСТИТУТЫ (замер на {inst.get('as_of')}): " + "; ".join(row))
    except Exception as e:  # noqa: BLE001
        logger.warning("sector_barometer: институты недоступны (%s)", type(e).__name__)
    return "\n".join(parts)


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
        # Окно по ДАТЕ, а не по числу точек. Было `LIMIT 90` в расчёте на дневной ряд,
        # но товарные ряды Всемирного банка — МЕСЯЧНЫЕ (121 точка за 10 лет), и 90
        # точек означало базу семилетней давности. Барометр на бою выдал «цены на
        # золото выросли на 208.6% относительно прошлого периода» — рост за семь лет,
        # поданный как недавний скачок. База теперь всегда подписана датой, чтобы
        # модель не могла принять её за «недавно».
        rows = db.execute(text("""
            SELECT value, as_of FROM macro_data_points
            WHERE indicator_code = :k AND metric = 'level'
              AND as_of >= (CURRENT_DATE - INTERVAL '400 days')
            ORDER BY as_of DESC
        """), {"k": k}).fetchall()
        if not rows:
            continue
        cur, cur_d = float(rows[0][0]), rows[0][1]
        old, old_d = (float(rows[-1][0]), rows[-1][1]) if len(rows) > 1 else (cur, cur_d)
        delta = ((cur - old) / old * 100) if old else 0.0
        title = db.execute(text("SELECT title FROM macro_indicators WHERE code = :k"),
                           {"k": k}).scalar() or k
        out.append(f"  {title}: {cur:g} (на {cur_d}); изменение {delta:+.1f}% "
                   f"относительно {old_d} — это база сравнения, НЕ «недавно»")
    return out



def _sector_financials(db: Session, tickers: list[str], limit: int = 12) -> tuple[list[str], dict]:
    """НАШИ числа по компаниям отрасли: выручка и чистая прибыль последнего года.

    🔴 Владелец, 2026-08-10: барометр написал «YDEX — убыток 51 млрд руб.», хотя у нас
    в карточке чистая прибыль 79,6 млрд и растёт. Число пришло из пересказа новости в
    ленте: своих канонических чисел барометр НЕ ВИДЕЛ вовсе — только отчётность-дайджесты
    и статьи. Пересказ всегда проигрывает собственным данным (CLAUDE.md: числа карточки —
    из financials.json, единый источник), поэтому кладём их прямо во вход и возвращаем
    вторым значением карту «тикер → прибыль» для гейта.
    """
    import json as _json
    from pathlib import Path
    root = Path(__file__).parent.parent.parent / "companies"
    lines, profits = [], {}
    for t in tickers[:limit * 3]:
        f = root / t / "financials.json"
        if not f.exists():
            continue
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        inc = data.get("income_statement") or {}
        rev, prof = inc.get("revenue") or [], inc.get("net_profit") or []
        last_p = next((v for v in reversed(prof) if isinstance(v, (int, float))), None)
        prev_p = next((v for v in reversed(prof[:-1]) if isinstance(v, (int, float))), None)
        last_r = next((v for v in reversed(rev) if isinstance(v, (int, float))), None)
        if last_p is None and last_r is None:
            continue
        profits[t] = last_p
        trend = ""
        if last_p is not None and prev_p not in (None, 0):
            trend = " (рост)" if last_p > prev_p else " (снижение)"
        lines.append(f"  {t}: выручка {last_r if last_r is not None else '—'} млн, "
                     f"чистая прибыль {last_p if last_p is not None else '—'} млн{trend}")
        if len(lines) >= limit:
            break
    return lines, profits



def _sector_articles(db: Session, key: str, label: str, drivers: str, limit: int = 6) -> list[str]:
    """Материалы ленты для отрасли — два слоя, в порядке точности.

    1. Отраслевая лента (sector_digest): статья изначально пришла из отраслевого
       источника и отнесена к КОНКРЕТНОЙ отрасли — привязка точная.
    2. Добор из общей ленты по совпадению слов названия и драйверов — грубо, но
       ловит то, что попало в бизнес/макро-ленту и отраслевых источников не имеет.
    Второй слой оставлен именно как добор: он даёт ложные срабатывания, поэтому
    идёт ПОСЛЕ точного и только на остаток лимита."""
    cutoff = date.today() - timedelta(days=_WINDOW_DAYS)
    hits, seen = [], set()
    exact = (db.query(GeoDigestArticle)
             .filter(GeoDigestArticle.target == f"sec:{key}",
                     GeoDigestArticle.published_at >= cutoff)
             .order_by(GeoDigestArticle.published_at.desc()).limit(limit).all())
    for r in exact:
        seen.add(r.id)
        hits.append(f"  {r.published_at} [{r.source_key}] {r.title}: {(r.summary or '')[:250]}")
    # Добор включается ТОЛЬКО когда отраслевых материалов нет вовсе. Он ищет по
    # совпадению слов и потому шумит: с двумя совпадениями в материалы по транспорту
    # и металлургии всё равно попадали «Северная Корея заработала за время войны» и
    # «X5 объявила дату отчётности». Пока у отрасли есть свои источники — чужое не
    # подмешиваем; когда источников нет (девелопмент), лучше шумный контекст с
    # пометкой, чем пустой.
    if hits:
        return hits

    words = [w.lower() for w in (label + " " + drivers).replace(",", " ").split()
             if len(w) > 5][:12]
    if not words:
        return hits
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(("business", "macro")),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(60).all())
    for r in rows:
        if r.id in seen:
            continue
        blob = f"{r.title} {r.summary or ''}".lower()
        # Два РАЗНЫХ совпадения, не одно. При пороге в одно слово в материалы по
        # транспорту попадали «Северная Корея заработала за время войны» и «Трамп о
        # криптовалютах» — одного «санкцион» хватало. Отрасль про такую статью не
        # узнаёт ничего, а место в контексте она занимает.
        if sum(1 for w in set(words) if w[:6] in blob) >= 2:
            # Помечаем явно: это подобрано по словам из общей ленты, а не пришло от
            # отраслевого источника. Без пометки модель принимает такую строку за
            # отраслевой факт и строит на ней вывод о состоянии рынка.
            hits.append(f"  {r.published_at} (из общей ленты, отраслевая принадлежность "
                        f"НЕ подтверждена) {r.title}: {(r.summary or '')[:200]}")
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


_LOSS_RE = re.compile(r"убыт\w*|в минусе|отрицательн\w+ прибыл\w*", re.I)


def _check(items: list[dict], allowed: set[str],
           profits: dict[str, float | None] | None = None) -> tuple[list[str], list[str]]:
    bad, notes = [], []
    # 🔴 Проверка кодом: сказать «убыток» про компанию, у которой в НАШИХ данных
    # прибыль, — не стилистика, а ложный факт о бумаге (владелец, 2026-08-10: «у
    # Яндекса наоборот чистая прибыль выросла»). Уговорами это не лечится: число
    # приходит из пересказа новости и выглядит убедительно.
    for s in items:
        for field in ("headline", "losers", "what_happens", "for_investor"):
            txt = str(s.get(field) or "")
            for tk, prof in (profits or {}).items():
                if prof is None or prof <= 0 or tk not in txt:
                    continue
                # ищем слово об убытке рядом с тикером (в пределах 120 знаков)
                i = txt.find(tk)
                around = txt[max(0, i - 60): i + 120]
                if _LOSS_RE.search(around):
                    msg = (f"{s.get('key')}: «{tk}» назван убыточным, а в наших данных "
                           f"чистая прибыль {prof:.0f} млн — ложный факт")
                    if msg not in bad:
                        bad.append(msg)
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
    profits: dict[str, float | None] = {}
    for sec in secs:
        tickers = _sector_tickers(db, sec)
        allowed.update(tickers)
        earn = _sector_earnings(db, tickers)
        prices = _sector_prices(db, tickers)
        arts = _sector_articles(db, sec["key"], sec["label"], sec["drivers"])
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
        fin, profit_map = _sector_financials(db, tickers)
        profits.update(profit_map)
        if fin:
            b.append("НАШИ ЧИСЛА по компаниям отрасли (карточки платформы — единый "
                     "источник, они СИЛЬНЕЕ пересказов в ленте):\n" + "\n".join(fin))
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

    try:
        from app.services.macro_sector_playbook import drivers_digest
        drivers = drivers_digest()
    except Exception:  # noqa: BLE001
        drivers = ""
    system = (
        "Ты — отраслевой аналитик Basis (независимая аналитика для частного "
        "инвестора в РФ). Ты оцениваешь СОСТОЯНИЕ ОТРАСЛЕЙ российского рынка: где "
        "отрасль сейчас, куда движется и что это значит для того, кто держит её "
        "акции. Пиши простым языком, без академических терминов и без жаргона.\n\n"
        + _SPEC + (("\n\n" + drivers) if drivers else "")
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
    bad, notes = _check(items, allowed, profits)
    if bad:
        # 🔴 Ремонтный проход (2026-08-10). Без него брак означал «переносим ПРОШЛЫЙ
        # замер» — то есть ровно тот текст, из-за которого батч и забраковали: ложный
        # убыток Яндекса продолжал висеть на витрине. Один проход: показываем замечания
        # и просим исправить ровно их, дальше честный перенос.
        logger.warning("sector_barometer: батч «%s» — ремонт по замечаниям: %s", name, bad[:4])
        fix = ("\n\nТвой предыдущий ответ забракован проверкой кодом. Замечания:\n"
               + "\n".join(f"- {b}" for b in bad)
               + "\n\nВерни ПОЛНЫЙ JSON того же формата, исправив ровно эти места. "
                 "Если названа убыточной компания, у которой в блоке «НАШИ ЧИСЛА» "
                 "прибыль, — убери это утверждение и не заменяй его другим домыслом: "
                 "бери число из наших данных. Остальное сохрани.")
        try:
            out2 = llm.complete(system, user + fix, json_mode=True, thinking=True,
                                model=llm.pro_model(), max_tokens=7000, temperature=0.2)
            items2 = (out2 or {}).get("sectors") if isinstance(out2, dict) else None
            items2 = [s for s in (items2 or []) if isinstance(s, dict) and s.get("key") in keys]
            if items2:
                bad2, notes2 = _check(items2, allowed, profits)
                if not bad2:
                    return items2, [f"батч «{name}»: починен после гейта"] + \
                        [f"батч «{name}»: {n}" for n in notes2]
                bad = bad2
        except llm.LLMError as e:
            bad = bad + [f"ремонт не удался: {e}"]
        return [], [f"батч «{name}» отклонён: {b}" for b in bad] + notes
    return items, [f"батч «{name}»: {n}" for n in notes]


def rebuild(db: Session) -> BarometerVersion | None:
    macro = _macro_frame(db)
    # Связка со средой: гео-флаги по отраслям и замеры институтов. Идёт в ТОТ ЖЕ
    # контекст, что макро-рамка, — чтобы вердикт отрасли не расходился с тем, что
    # платформа говорит в соседних разделах.
    env = _env_frame(db)
    if env:
        macro = macro + "\n\n" + env
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
