"""Проверки пайплайна «Финансы карточки».

Каждая проверка привязана к РЕАЛЬНОМУ инциденту проекта — в поле `rationale`
написано, к какому. Проверка без инцидента за спиной обычно ловит гипотетику и
шумит; такие сюда не добавляем.

🔴 Правило кода: сначала спрашиваем «есть ли что проверять», и если нечего —
возвращаем SKIP, а не молчаливый OK.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from app.services import units
from app.services.quality.contract import (Check, CheckOutcome, Resolution, Severity,
                                           fail, ok, skip)

_REGISTRY: dict[str, set[str]] | None = None

ROOT = Path(__file__).resolve().parents[4]
COMPANIES = ROOT / "backend" / "companies"
SCRIPTS = ROOT / "backend" / "scripts"

# Легаси-аудиты — зрелые банки проверок, переиспользуем, а не переписываем.
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _legacy_audit():
    import audit_financials
    return audit_financials


def _legacy_cross_tab():
    import audit_cross_tab
    return audit_cross_tab


# ─────────────────────────── помощники ───────────────────────────

def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def by_year(card: dict, *path: str) -> dict[int, float]:
    """Ряд карточки как {год: значение}. Понимает и список (выровненный по
    meta.fiscal_years), и словарь {'2024': 1234}."""
    years = (card.get("meta") or {}).get("fiscal_years") or []
    node: Any = card
    for key in path:
        if not isinstance(node, dict):
            return {}
        node = node.get(key)
    out: dict[int, float] = {}
    if isinstance(node, list):
        for i, y in enumerate(years):
            if i < len(node) and (v := _num(node[i])) is not None:
                out[int(y)] = v
    elif isinstance(node, dict):
        for k, v in node.items():
            if re.fullmatch(r"(19|20)\d{2}", str(k)) and (n := _num(v)) is not None:
                out[int(k)] = n
    return out


_LEGAL_FORMS = {"пао", "оао", "ао", "зао", "ооо", "гк", "нк", "мкпао", "публичное",
                "акционерное", "общество", "компания", "группа", "холдинг", "банк",
                "корпорация", "концерн", "им", "россии"}

# Отраслевые и обиходные слова: встречаются в названии, но эмитента НЕ опознают.
# «ГлобалТрак Менеджмент» ловился на фразе «менеджмент не даёт прогноз», а
# «European Medical Centre» — на «MD Medical Group». Частотный фильтр их не
# берёт (слово может быть всего у одной компании), поэтому список явный.
_GENERIC_WORDS = {"менеджмент", "management", "медикал", "medical", "european",
                  "centre", "center", "group", "груп", "групп", "холдинг", "holding",
                  "капитал", "capital", "инвест", "invest", "investments", "финанс",
                  "finance", "энерго", "энергия", "energy", "телеком", "telecom",
                  "технологии", "technologies", "систем", "системы", "systems",
                  "продукт", "продукты", "трейд", "trade", "сервис", "service",
                  "стандарт", "промышленн", "торговый", "торговая", "русский",
                  "российски", "национальн", "объединенн", "объединённ"}


def name_tokens(card: dict, ticker: str) -> set[str]:
    """Слова, по которым узнаётся эмитент: имя без организационной формы + тикер.

    🔴 Порог длины 3, а не 4: иначе «МТС» выпадает и собственная отчётность
    компании объявляется чужой. Обиходное сокращение («Сбербанк» → «СБЕР»)
    ловится сравнением по первым 4 буквам, а не полным совпадением."""
    name = ((card.get("meta") or {}).get("name") or "").lower()
    words = {w for w in re.split(r"[^\wёa-z]+", name)
             if len(w) >= 3 and w not in _LEGAL_FORMS and w not in _GENERIC_WORDS}
    words.add(ticker.lower())
    return words


def _mentions_issuer(text: str, tokens: set[str], *, strict: bool = False) -> bool:
    """Назван ли эмитент в тексте.

    🔴 Совпадение — ТОЛЬКО по границам слов. Подстрока опознавала «ИнтерФакс»
    как «Интер РАО», «справедливая» как «ИВА», а односимвольный тикер «T» —
    вообще везде: 46 находок, из них почти все ложные.

    strict=False (свой эмитент): допускаем обиходное сокращение по первым
        четырём буквам («Сбербанк» → «СБЕР»); ошибиться в эту сторону дёшево.
    strict=True (чужой эмитент): только целое слово длиной от пяти букв —
        улика должна быть уликой.
    """
    for t in tokens:
        if strict and len(t) < 5:
            continue
        if re.search(rf"(?<![\wё]){re.escape(t)}(?![\wё])", text):
            return True
        if not strict and len(t) > 4 and re.search(rf"(?<![\wё]){re.escape(t[:4])}", text):
            return True
    return False


# Документ ОТЧЁТНОСТИ обязан называть эмитента. Отраслевой обзор, консенсус
# аналитиков или внутренний конфиг макропараметров — законно не называют, и
# требовать этого от них значит генерировать шум вместо находок.
_REPORTING_WORDS = ("отчётност", "отчетност", "мсфо", "рсбу", "годовой отчёт",
                    "годовой отчет", "финансовая отчётность", "презентац",
                    "quarterly", "annual report", "ifrs")


# Единицы, в которых карточка и первичка могут быть записаны независимо друг от
# друга. 🔴 Без приведения сверка объявляет дефектом обычную разницу «млн против
# тыс.» — на первом прогоне так набралось 18 ложных находок из 80.
_UNIT_FACTOR = {"тыс": 1e3, "тыс.": 1e3, "тысяч": 1e3, "тыс. руб": 1e3,
                "млн": 1e6, "млн.": 1e6, "миллион": 1e6, "млн руб": 1e6,
                "млрд": 1e9, "млрд.": 1e9, "миллиард": 1e9, "млрд руб": 1e9,
                "ед": 1.0, "руб": 1.0}


def unit_factor(node: dict) -> float | None:
    """Множитель единицы измерения карточки/первички; None — не распознана."""
    raw = ((node.get("meta") or {}).get("unit") or "").strip().lower()
    if not raw:
        return None
    if raw in _UNIT_FACTOR:
        return _UNIT_FACTOR[raw]
    for key, factor in _UNIT_FACTOR.items():
        if raw.startswith(key):
            return factor
    return None


def _load_extracted(ticker: str) -> dict | None:
    p = COMPANIES / ticker / "sources" / "extracted_financials.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ─────────────────────────── проверки ───────────────────────────

def _c_arithmetic(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Арифметика карточки: баланс, части-целое, копии годов, скачки единиц и т.д.
    Обёртка над зрелым scripts/audit_financials.py."""
    card = payload["card"]
    if not (card.get("meta") or {}).get("fiscal_years"):
        yield skip(C_ARITHMETIC, subject, "в meta нет fiscal_years — проверять нечего")
        return
    found = _legacy_audit().audit(card, subject)
    hard = [(k, t) for sev, k, t in found if sev == "!"]
    if hard:
        kinds = sorted({k for k, _ in hard})
        yield fail(C_ARITHMETIC, subject,
                   f"{len(hard)} груб. наруш. арифметики: {', '.join(kinds)}",
                   kinds=kinds, examples=[t for _, t in hard[:3]])
    else:
        yield ok(C_ARITHMETIC, subject, soft=len(found))


def _c_profit_vs_revenue(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Прибыль несопоставима с выручкой — типовой след ошибки масштаба при
    извлечении (модель отдала млрд там, где карточка в млн)."""
    card = payload["card"]
    if card.get("bank_pnl") or card.get("bank_balance"):
        yield skip(C_PROFIT_VS_REVENUE, subject, "банк: строка «выручка» иная по смыслу",
                   by_design=True)
        return
    rev = by_year(card, "income_statement", "revenue")
    npr = by_year(card, "income_statement", "net_profit")
    common = sorted(set(rev) & set(npr))
    if not common:
        yield skip(C_PROFIT_VS_REVENUE, subject, "нет пары выручка/прибыль ни за один год")
        return
    bad = [(y, rev[y], npr[y]) for y in common if rev[y] > 0 and abs(npr[y]) > 3 * rev[y]]
    if bad:
        y, r, p = bad[0]
        yield fail(C_PROFIT_VS_REVENUE, subject,
                   f"{y}: прибыль {p:,.0f} более чем втрое превышает выручку {r:,.0f} "
                   f"— похоже на разный масштаб строк",
                   years=[b[0] for b in bad])
    else:
        yield ok(C_PROFIT_VS_REVENUE, subject, checked_years=len(common))


_SOURCE_LINES = (
    ("income_statement", "revenue"), ("income_statement", "net_profit"),
    ("balance_sheet", "total_assets"), ("balance_sheet", "total_equity"),
    ("cash_flow", "operating_cash_flow"),
)


def _c_source_match(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Витрина против первички: сверяем financials.json с НЕЗАВИСИМЫМ извлечением
    из отчётности (sources/extracted_financials.json, добытчик report-fetcher).
    Единственная проверка набора, у которой есть внешняя точка отсчёта."""
    card, ext = payload["card"], payload.get("extracted")
    if not ext:
        yield skip(C_SOURCE_MATCH, subject, "нет sources/extracted_financials.json")
        return
    # Приводим первичку к единицам карточки. Не распознали единицу — НЕ сверяем:
    # молча сравнить млн с тысячами хуже, чем честно сказать «не знаю».
    f_card, f_ext = unit_factor(card), unit_factor(ext)
    if f_card is None or f_ext is None:
        yield skip(C_SOURCE_MATCH, subject,
                   f"единица не распознана (витрина «{(card.get('meta') or {}).get('unit')}», "
                   f"первичка «{(ext.get('meta') or {}).get('unit')}»)")
        return
    к = f_ext / f_card
    compared, diffs = 0, []
    for path in _SOURCE_LINES:
        a, b = by_year(card, *path), by_year(ext, *path)
        for y in sorted(set(a) & set(b)):
            av, bv = a[y], b[y] * к
            if max(abs(av), abs(bv)) < 1:      # нули и копейки не сверяем
                continue
            compared += 1
            denom = max(abs(bv), 1.0)
            if abs(av - bv) / denom > 0.02:    # 2% — округления отчётности, не дефект
                diffs.append((".".join(path), y, av, bv, (av - bv) / denom * 100))
    if not compared:
        yield skip(C_SOURCE_MATCH, subject, "нет ни одной общей строки-года с первичкой")
        return

    # 🔴 Разные ЧИСЛА и разные ЕДИНИЦЫ — разные диагнозы, и чинятся по-разному.
    # Если почти все строки расходятся ровно в 1000 раз, дело не в данных, а в
    # том, что первичка записана не в тех единицах, что объявлены в её meta.
    if len(diffs) >= max(3, int(compared * 0.6)):
        ratios = sorted(abs(av / bv) for _, _, av, bv, _ in diffs if bv)
        if ratios:
            median = ratios[len(ratios) // 2]
            for power in (1e-9, 1e-6, 1e-3, 1e3, 1e6, 1e9):
                if abs(median / power - 1) < 0.05:
                    yield fail(C_SOURCE_MATCH, subject,
                               resolution=Resolution.LOCATED,   # виновник назван: meta первички
                               message=f"первичка записана в единицах, отличных от объявленных: "
                               f"расхождение ×{power:,.0f} на {len(diffs)} из {compared} строк "
                               f"(meta первички говорит «{(ext.get('meta') or {}).get('unit')}»)",
                               kind="unit_mismatch", factor=power,
                               compared=compared, diffs=len(diffs))
                    return

    if diffs:
        line, y, av, bv, pct = max(diffs, key=lambda d: abs(d[4]))
        yield fail(C_SOURCE_MATCH, subject,
                   # арбитр есть: первичный отчёт эмитента
                   resolution=Resolution.LOCATED,
                   message=f"расходится с первичкой в {len(diffs)} из {compared} сверок; худшее — "
                   f"{line} за {y}: карточка {av:,.0f} против {bv:,.0f} в отчёте ({pct:+.0f}%)",
                   compared=compared, diffs=len(diffs),
                   worst=[line, y, av, bv])
    else:
        yield ok(C_SOURCE_MATCH, subject, compared=compared)


def issuer_registry() -> dict[str, set[str]]:
    """{тикер: слова-опознаватели} по всем карточкам платформы. Кэшируется."""
    global _REGISTRY
    if _REGISTRY is None:
        reg: dict[str, set[str]] = {}
        for path in COMPANIES.glob("*/financials.json"):
            try:
                card = json.loads(path.read_text())
            except Exception:
                continue
            reg[path.parent.name] = name_tokens(card, path.parent.name)
        # 🔴 Слово, встречающееся у нескольких эмитентов, эмитента не опознаёт:
        # «груп» роднит «ЭН+ ГРУП» с любым «Group» в заголовке. Стоп-лист руками
        # тут вести бессмысленно — отсекаем по частоте.
        seen: dict[str, int] = {}
        for toks in reg.values():
            for t in toks:
                seen[t] = seen.get(t, 0) + 1
        reg = {t: {w for w in toks if seen[w] <= 2} for t, toks in reg.items()}
        _REGISTRY = reg
    return _REGISTRY


def _c_source_issuer(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Источник принадлежит ЧУЖОМУ эмитенту. Реальные случаи: Роснефть → РуссНефть,
    Акрон → аналитика Сбера, Белуга → cbonds. Чужие цифры правдоподобны, поэтому
    ловить их надо по принадлежности документа, а не по виду чисел.

    🔴 Проверка спрашивает «названа ли в документе ЧУЖАЯ компания», а не «названа
    ли наша». Первая версия спрашивала второе и дала 48 находок, почти все
    ложные: латиница в имени («Acron»), разборы третьих лиц (Smart-lab, БКС),
    заголовки без имени вообще. Отсутствие нашего имени — не улика; присутствие
    чужого — улика."""
    card = payload["card"]
    meta = card.get("meta") or {}
    docs: list[dict] = []
    src = meta.get("source")
    if isinstance(src, dict):
        for key in ("supplementary_docs", "docs", "primary_docs"):
            docs += [d for d in (src.get(key) or []) if isinstance(d, dict)]
    for key in ("sources",):
        docs += [d for d in (meta.get(key) or []) if isinstance(d, dict)]
        docs += [d for d in (card.get(key) or []) if isinstance(d, dict)]
    titled = [d for d in docs if (d.get("doc_title") or d.get("title"))]
    if not titled:
        yield skip(C_SOURCE_ISSUER, subject, "у источников нет названий документов")
        return
    tokens = name_tokens(card, subject)
    if not tokens:
        yield skip(C_SOURCE_ISSUER, subject, "не удалось выделить имя эмитента")
        return
    registry = issuer_registry()
    alien, reporting = [], 0
    for d in titled:
        title = d.get("doc_title") or d.get("title")
        text = f"{title} {d.get('url') or ''}".lower()
        if not any(w in text for w in _REPORTING_WORDS):
            continue                      # не документ отчётности — не наш случай
        reporting += 1
        if _mentions_issuer(text, tokens):
            continue                      # наш эмитент назван — вопрос закрыт
        others = sorted({t for t, toks in registry.items()
                         if t != subject and _mentions_issuer(text, toks, strict=True)})
        # чужие тикеры-«соседи» (обычка/преф одного эмитента) уликой не считаются
        others = [t for t in others if not (t.startswith(subject[:4]) or subject.startswith(t[:4]))]
        if others:
            alien.append(f"{title[:80]} → {', '.join(others[:2])}")
    if not reporting:
        yield skip(C_SOURCE_ISSUER, subject, "среди источников нет документов отчётности")
        return
    if alien:
        yield fail(C_SOURCE_ISSUER, subject,
                   f"{len(alien)} из {reporting} документов отчётности названы по ЧУЖОМУ "
                   f"эмитенту: {alien[0]}",
                   alien=alien[:3], checked=reporting)
    else:
        yield ok(C_SOURCE_ISSUER, subject, checked=reporting)


def _c_freshness(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Свежесть: последний отчётный год отстал больше чем на один полный год."""
    card, today_year = payload["card"], payload["today_year"]
    years = (card.get("meta") or {}).get("fiscal_years") or []
    nums = [int(y) for y in years if isinstance(y, (int, float))]
    if not nums:
        yield skip(C_FRESHNESS, subject, "нет fiscal_years")
        return
    last = max(nums)
    if last <= today_year - 2:
        yield fail(C_FRESHNESS, subject,
                   f"последний отчётный год {last} при текущем {today_year} — карточка отстала",
                   last_year=last)
    else:
        yield ok(C_FRESHNESS, subject, last_year=last)


def _c_return_units(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Смешанные единицы рентабельностей: у части компаний roe/roa/ros лежат в
    долях, у части — в процентах. Порог «больше 1.5 значит проценты» опасен
    (реальные 0,88% раздуваются в 88%), поэтому единицы определяем ПЕРЕСЧЁТОМ."""
    card = payload["card"]
    returns = card.get("returns") or {}
    checked, mixed = [], []
    for key in ("roe", "roa", "ros"):
        series = returns.get(key)
        if not isinstance(series, list):
            continue
        scale = units._scale_for_metric(card, key, series)
        if scale is None:
            continue
        checked.append(key)
        if scale != 1.0:
            mixed.append((key, scale))
    if not checked:
        yield skip(C_RETURN_UNITS, subject, "рентабельности нельзя сверить пересчётом")
        return
    if mixed:
        yield fail(C_RETURN_UNITS, subject,
                   f"записаны в долях, а не процентах: {', '.join(k for k, _ in mixed)}",
                   mixed=[k for k, _ in mixed], checked=checked)
    else:
        yield ok(C_RETURN_UNITS, subject, checked=checked)


def _shift_all_series(card: dict, factor: float) -> dict:
    """Копия карточки, где все числовые ряды отчётных блоков умножены на factor.
    Нужна для само-пробы сверки: см. _c_cross_tab."""
    for group in ("income_statement", "balance_sheet", "cash_flow", "bank_pnl",
                  "bank_balance", "bank_metrics"):
        node = card.get(group)
        if not isinstance(node, dict):
            continue
        for key, series in node.items():
            if key.endswith("_note") or not isinstance(series, list):
                continue
            node[key] = [v * factor if isinstance(v, (int, float)) and not isinstance(v, bool)
                         else v for v in series]
    return card


_NCI_MARKERS = ("nci", "minority", "noncontrol", "non_controlling", "attributable",
                "миноритар", "неконтролир")


def _has_nci_field(card: dict) -> bool:
    """Структурный признак неконтролирующих долей — ТОЛЬКО в именах полей.

    🔴 Не искать по тексту всего файла: слово «неконтролирующие» встречается в
    прозе где угодно, и такой фильтр объявляет законным всё подряд. Проверено
    сессией «статус обновления данных»: поиск по файлу пометил «может быть
    законно» все 11 строк со сменой знака — то есть не проверял ничего."""
    nodes = [card.get("income_statement"), card.get("bank_pnl"),
             (card.get("balance_sheet") or {}).get("equity")]
    for node in nodes:
        if isinstance(node, dict) and any(
                any(m in str(k).lower() for m in _NCI_MARKERS) for k in node):
            return True
    return False


def _tax_rows(card: dict):
    """Годы, расчёт «до налога + налог», расхождение и подпись ошибки знака."""
    pre_tax = by_year(card, "income_statement", "pre_tax_profit")
    tax = by_year(card, "income_statement", "income_tax")
    net = by_year(card, "income_statement", "net_profit")
    years = sorted(set(pre_tax) & set(tax) & set(net))
    rows = []
    for y in years:
        best = min((pre_tax[y] + sign * tax[y] for sign in (1, -1)),
                   key=lambda c: abs(c - net[y]))
        ratio = abs(best - net[y]) / max(abs(net[y]), 1.0)
        size_match = abs(abs(best) - abs(net[y])) / max(abs(net[y]), 1.0) < 0.10
        flipped = size_match and (best > 0) != (net[y] > 0) and min(abs(best), abs(net[y])) > 1
        rows.append((y, ratio, flipped, best, net[y]))
    return rows


# Насколько велика может быть «собственная база» карточки, если законная причина
# в схеме НЕ отмечена. 🔴 Без этого потолка база впитывает дефект и проверка
# перестаёт его видеть: у БЛНГ сопоставимых лет всего два, ОБА были битыми,
# медиана расхождения равнялась самому расхождению — и порог «втрое выше базы»
# не срабатывал никогда. Ретро-прогон на данных до починки это и показал: без
# потолка проверка возвращала «ок» по эталонному дефекту, ради которого её и
# писали. Стабильность ряда не доказывает его правоту.
_UNEXPLAINED_BASELINE_CAP = 0.10


def _tax_anomalies(rows, *, explained: bool = False):
    """Аномальные годы и база карточки.

    Большая база законна, только если расхождение объяснено СТРУКТУРНО (в схеме
    есть поле неконтролирующих долей): тогда «прибыль акционеров меньше общей»
    — это конвенция, и она держится из года в год. Если такого поля нет, база
    ограничивается потолком, иначе карточка сама себе выписывает индульгенцию.
    """
    ratios = sorted(r for _, r, _, _, _ in rows)
    baseline = ratios[len(ratios) // 2]
    effective = baseline if explained else min(baseline, _UNEXPLAINED_BASELINE_CAP)
    return [r for r in rows if r[1] > max(0.25, 3 * effective)], baseline


def _roe_corroborates(card: dict, year: int, computed: float) -> bool | None:
    """Согласна ли рентабельность капитала со ЗНАКОМ расчётной прибыли.

    🔴 Единственный НЕЗАВИСИМЫЙ свидетель внутри файла. Проза таким свидетелем не
    является: она пересказывает то же поле и по построению производна от него —
    ссылаться на неё всё равно что ссылаться на само поле (довод сессии «статус
    обновления данных»). А `returns.roe` считается отдельно и у БЛНГ был −18,3
    при +190 в поле, то есть считался от ПРАВИЛЬНОГО числа.

    True — подтверждает расчёт (виновник — само поле прибыли);
    False — подтверждает файл (противоречие где-то ещё);
    None — свидетеля нет."""
    roe = by_year(card, "returns", "roe")
    value = roe.get(year)
    if value is None or abs(value) < 1e-9:
        return None
    return (value > 0) == (computed > 0)


def _c_tax_sign(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Ошибка ЗНАКА чистой прибыли: величина сходится с «до налога + налог»,
    а знак противоположный. Резкая подпись, законной причины не имеет.
    Так поймался Иркут-2022: −27 253 расчётных против +27 300 в файле."""
    card = payload["card"]
    rows = _tax_rows(card)
    if len(rows) < 2:
        yield skip(C_TAX_SIGN, subject, "нет двух лет с прибылью до налога, налогом и чистой")
        return
    anomalies, _ = _tax_anomalies(rows, explained=_has_nci_field(card))
    # 🔴 Наличие доли неконтролирующих здесь НЕ оправдание: она объясняет разницу
    # в ВЕЛИЧИНЕ (прибыль акционеров меньше общей), но не перевёрнутый знак при
    # совпадающей величине. Гашение по НКД стоило проверке трёх носителей из
    # четырёх на мутационном стенде — то есть на большинстве карточек ошибка
    # знака прошла бы мимо.
    flips = [a for a in anomalies if a[2]]
    if flips:
        y, _, _, best, actual = flips[0]
        witness = _roe_corroborates(card, y, best)
        if witness is True:
            tail = ("; рентабельность капитала за тот же год посчитана от расчётной "
                    "величины — значит неверно само поле прибыли")
            resolution = Resolution.LOCATED
        else:
            tail = ("; независимого свидетеля нет — «перевёрнут знак прибыли» и «перевёрнут "
                    "знак прибыли до налога» арифметически неразличимы. Нужен первичный "
                    "отчёт, а не правка по догадке")
            resolution = Resolution.UNRESOLVED
        yield fail(C_TAX_SIGN, subject,
                   f"{y}: прибыль до налога и налог дают {best:,.0f}, а в файле {actual:,.0f} — "
                   f"величина та же, знак противоположный{tail}",
                   resolution=resolution,
                   years=[a[0] for a in flips], has_nci_field=_has_nci_field(card))
    else:
        yield ok(C_TAX_SIGN, subject, checked_years=len(rows))


def _c_tax_identity(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Прибыль до налога + налог = чистая прибыль — чистая арифметика.

    Сильнее сверки с мостом и с прозой: не требует ни суждения, ни разбора
    текста. Знак налога в файлах непоследователен, поэтому пробуем оба.

    🔴 Расхождение НЕ равно дефекту, и это главное в проверке. Консолидированная
    отчётность даёт законные причины: прибыль акционеров без неконтролирующих
    долей и прекращённая деятельность (у Мечела-2020 продажа Эльги даёт +808
    при убытке до налога −37 625 — и это верно). Сырой прогон даёт 169 строк у
    72 компаний; публиковать их как находки нельзя, раздутая корзина прячет
    настоящее. Поэтому:
      • условность консолидации держится ИЗ ГОДА В ГОД — сравниваем год не с
        нулём, а с собственной базой карточки (медианой расхождения);
      • грубо — только резкая подпись ошибки ЗНАКА: величина совпадает (в
        пределах 10%), а знак противоположен. Так поймался Иркут-2022:
        −27 253 расчётных против +27 300 в файле;
      • всё остальное — мягко, с честной оговоркой, что законную причину
        отличить нечем: поля «прекращённая деятельность» в файлах НЕТ вообще.
    Найдено сессией «статус обновления данных» на разборе БЛНГ, 11.09.2026."""
    card = payload["card"]
    if len(_tax_rows(card)) < 2:
        yield skip(C_TAX_IDENTITY, subject, "нет двух лет с прибылью до налога, налогом и чистой")
        return

    rows = _tax_rows(card)
    anomalies, baseline = _tax_anomalies(rows, explained=_has_nci_field(card))
    if not anomalies:
        yield ok(C_TAX_IDENTITY, subject, checked_years=len(rows),
                 baseline=round(baseline, 3))
        return

    y, ratio, _, best, actual = max(anomalies, key=lambda a: a[1])
    yield fail(C_TAX_IDENTITY, subject,
               resolution=Resolution.UNRESOLVED,
               message=f"{y}: расчёт {best:,.0f} против {actual:,.0f} в файле ({ratio:.0%} при базе "
               f"карточки {baseline:.0%}) — не сходится ни при одном знаке налога. Законные "
               f"причины (прекращённая деятельность, доля неконтролирующих) в файле не "
               f"отмечены: такого поля в схеме нет, отличить нечем",
               kind="unexplained", years=[a[0] for a in anomalies],
               has_nci_field=_has_nci_field(card))


def _c_adjusted_bridge(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Отчётная прибыль против МОСТА НОРМАЛИЗАЦИИ в том же файле.

    Мост перечисляет разовые статьи, которые прибавляются к отчётной прибыли,
    чтобы получить нормализованную: reported + Σ добавок = adjusted. Если
    равенство не сходится, битым может быть любой из трёх, но противоречие
    внутри одного файла есть точно.

    Ловит случай, до которого не добирается сверка с прозой: у БЛНГ отчётная
    прибыль 2024 стоит +190 млн, а мост (доля в убытке ММК-Уголь −2066 млн,
    добавка +1549,8) даёт нормализованную −491,2 — то есть отчётный ряд не
    может быть верным. Проверка чисто файловая: ни БД, ни разбора текста.
    Найдено сессией «статус обновления данных», 11.09.2026."""
    card = payload["card"]
    adj = card.get("adjusted") or {}
    bridge = adj.get("bridge")
    npa = by_year({**card, "adjusted": adj}, "adjusted", "net_profit_adj")
    reported = by_year(card, "income_statement", "net_profit")
    if not isinstance(bridge, list) or not bridge or not npa or not reported:
        yield skip(C_ADJ_BRIDGE, subject, "нет моста нормализации или нормализованной прибыли")
        return
    # 🔴 Сумма добавки лежит под ДВУМЯ разными именами: у большинства карточек
    # это `amount`, у части — пара `amount_gross_mln`/`amount_net_back_mln`
    # (нетто после налога). Один смысл под двумя именами — сам по себе изъян
    # контракта данных; проверка обязана понимать оба, иначе молча пропустит
    # половину карточек (первая версия так и делала: 202 карточки с мостом,
    # проверка отработала на единицах).
    add_by_year: dict[int, float] = {}
    for item in bridge:
        if not isinstance(item, dict) or not item.get("added_back"):
            continue
        # 🔴 Мост несёт статьи для РАЗНЫХ величин: часть нормализует прибыль,
        # часть — денежный поток (capex, оборотный капитал). Суммировать их
        # вместе нельзя. У ЛУКОЙЛа именно это давало ложную находку: с одной
        # прибыльной статьёй равенство сходится ТОЧНО (−1 064 269 + 1 157 269 =
        # 93 000), а вместе с capex-статьёй — нет. Явный признак (`fcf_line`)
        # проставлен лишь у двух статей из 1064, поэтому дополняем разбором
        # формулировки — и честно помним, что это эвристика.
        if item.get("fcf_line"):
            continue
        text = str(item.get("item") or "").lower()
        if any(w in text for w in ("capex", "капзатрат", "капитальн", "fcf",
                                   "денежн", "оборотн")):
            continue
        year = item.get("year")
        amount = item.get("amount_net_back_mln")
        if not isinstance(amount, (int, float)):
            amount = item.get("amount")
        if isinstance(year, int) and isinstance(amount, (int, float)):
            add_by_year[year] = add_by_year.get(year, 0.0) + float(amount)
    years = sorted(set(add_by_year) & set(npa) & set(reported))
    if not years:
        yield skip(C_ADJ_BRIDGE, subject, "мост не пересекается по годам с рядами прибыли")
        return
    # Срабатываем не на любом расхождении: мост — конструкция с суждением
    # (налоговый эффект, частичный зачёт), и мелкий зазор законен. Дефект — это
    # РАЗНЫЙ ЗНАК (нормализация не может превратить прибыль в убыток простым
    # прибавлением) либо разрыв больше четверти величины.
    broken, minor = [], []
    for y in years:
        expected = reported[y] + add_by_year[y]
        actual = npa[y]
        gap = abs(expected - actual) / max(abs(actual), 1.0)
        sign_flip = (expected > 0) != (actual > 0) and min(abs(expected), abs(actual)) > 1
        (broken if (sign_flip or gap > 0.25) else minor).append(
            (y, reported[y], add_by_year[y], expected, actual, gap, sign_flip))
    # Отдельный диагноз: статья моста записана в других единицах, чем ряды
    # карточки (у Ленты карточка в млрд, а добавка — 950, то есть млн). Чинится
    # это не пересчётом прибыли, а исправлением статьи, поэтому и называть надо
    # иначе — иначе диагноз теряется в общей куче «не сходится».
    if broken:
        scale_off = [b for b in broken
                     if abs(b[2]) > 0 and abs(b[1]) > 0
                     and 300 < abs(b[2]) / max(abs(b[1]), 1e-9) < 3000]
        if len(scale_off) == len(broken):
            y, rep, add = scale_off[0][0], scale_off[0][1], scale_off[0][2]
            yield fail(C_ADJ_BRIDGE, subject,
                       f"{y}: добавка моста {add:+,.0f} примерно в тысячу раз крупнее самой "
                       f"прибыли {rep:,.0f} — статья записана в других единицах, чем ряды "
                       f"карточки (карточка в «{(card.get('meta') or {}).get('unit')}»)",
                       kind="unit_mismatch", years=[b[0] for b in broken])
            return

    if broken:
        y, rep, add, exp, act, gap, flip = max(broken, key=lambda b: b[5])
        why = "знак не совпадает" if flip else f"разрыв {gap:.0%}"
        yield fail(C_ADJ_BRIDGE, subject,
                   resolution=Resolution.UNRESOLVED,
                   message=f"{y}: отчётная прибыль {rep:,.0f} + добавки моста {add:+,.0f} = {exp:,.0f}, "
                   f"а нормализованная в файле {act:,.0f} ({why}) — противоречие внутри файла",
                   years=[b[0] for b in broken], checked_years=len(years),
                   sign_flip=any(b[6] for b in broken))
    else:
        yield ok(C_ADJ_BRIDGE, subject, checked_years=len(years),
                 minor_gaps=len(minor))


def _c_cross_tab(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Стыки: числа в прозе вкладок против financials.json. Системный вывод
    аудита платформы — ломается не аналитика, а согласованность между вкладками.

    🔴 Сверяем карточку ИЗ PAYLOAD, а не с диска. Первая версия звала
    audit_company(tdir), который сам читает файл, — и мутационный стенд не мог
    её проверить в принципе: испорченная в памяти карточка до проверки просто
    не доезжала. Проверка, которую нечем доказать, ничем не лучше отсутствующей.

    🔴 audit_company возвращает пустой список И когда всё чисто, И когда сверять
    было нечего (нет прозы). Наличие материала проверяем САМИ."""
    card = payload["card"]
    tdir = COMPANIES / subject
    prose = [f for f in ("business_model.md", "financials_summary.md") if (tdir / f).exists()]
    if not prose:
        yield skip(C_CROSS_TAB, subject, "нет прозы вкладок для сверки")
        return
    ct = _legacy_cross_tab()
    years, facts = ct.load_facts(card)
    if not years:
        yield skip(C_CROSS_TAB, subject, "в карточке нет годов для сверки")
        return
    meta = card.get("meta") or {}
    findings = []
    for fname in prose:
        findings += ct.check_tables((tdir / fname).read_text(), years, facts, fname,
                                    (meta.get("currency") or "RUB").upper(),
                                    meta.get("reporting_standard") or "")
    hard = [f for f in findings if f.get("severity") in ("MISMATCH", "ERROR")]

    # 🔴 Само-проба: «ноль расхождений» бывает двух видов — «всё сошлось» и
    # «сверять было нечего» (проза без таблиц с числами, как у ГМК). Второе
    # выглядит зелёным и молчит. Отличаем их так: подсовываем заведомо сдвинутые
    # числа — если и на них тишина, значит проверка не сравнила НИЧЕГО.
    if not hard:
        probe = _shift_all_series(json.loads(json.dumps(card)), 1.37)
        probe_years, probe_facts = ct.load_facts(probe)
        probe_findings = []
        for fname in prose:
            probe_findings += ct.check_tables((tdir / fname).read_text(), probe_years,
                                              probe_facts, fname,
                                              (meta.get("currency") or "RUB").upper(),
                                              meta.get("reporting_standard") or "")
        if not any(f.get("severity") == "MISMATCH" for f in probe_findings):
            yield skip(C_CROSS_TAB, subject,
                       "в прозе нет чисел, сопоставимых с financials.json "
                       "(сдвиг всех рядов на 37% тоже не даёт расхождений)")
            return

    if hard:
        # 🔴 Сортируем по diff_pct и печатаем именно его. Легаси-скрипт считает
        # расхождение УЖЕ с учётом кратностей (×1, ×1000, ×0.001), а печать
        # «в тексте 457 против 0.48 в данных» смешивала млн с млрд и делала
        # мелочь (5,5%) похожей на ошибку на порядок — из-за чего настоящий
        # кратный дефект терялся в списке рядом с ней.
        hard.sort(key=lambda f: f.get("diff_pct") or 0, reverse=True)
        f = hard[0]
        yield fail(C_CROSS_TAB, subject,
                   # 🔴 Проза карточки почти всегда производна от financials.json:
                   # она пересказывает число, а не свидетельствует о нём. Поэтому
                   # расхождение доказывает дрейф, но не говорит, какая сторона
                   # права (довод сессии «статус обновления данных»).
                   resolution=Resolution.UNRESOLVED,
                   message=f"{len(hard)} расхождений прозы с financials.json; худшее — "
                   f"{f.get('file')} {f.get('year') or ''} {f.get('metric')}: "
                   f"разница {f.get('diff_pct')}% (в тексте «{f.get('in_text')}», "
                   f"в данных {f.get('fact_bln')} млрд)",
                   mismatches=len(hard), files=prose,
                   worst_pct=f.get("diff_pct"),
                   all_pct=sorted((x.get("diff_pct") or 0) for x in hard)[::-1][:5])
    else:
        yield ok(C_CROSS_TAB, subject, files=prose, findings=len(findings))


# ─────────────────────────── реестр ───────────────────────────

C_ARITHMETIC = Check("fin.arithmetic", "Арифметика карточки сходится", Severity.HARD,
                     _c_arithmetic,
                     "Баланс Кузнецкого, копии годов Кармани, единицы Авангарда")
# 🔴 SOFT, а не HARD: разовая продажа актива (Лензолото) выглядит В ТОЧНОСТИ как
# ошибка масштаба — прибыль кратно выше выручки. Отличить их может человек или
# LLM по прозе, но не арифметика. Помечаем «посмотреть», а не «дефект».
C_PROFIT_VS_REVENUE = Check("fin.profit_vs_revenue", "Прибыль сопоставима с выручкой", Severity.SOFT,
                            _c_profit_vs_revenue,
                            "Ошибка масштаба при извлечении LLM: млрд вместо млн")
C_SOURCE_MATCH = Check("fin.source_match", "Витрина совпадает с первичкой", Severity.SOFT,
                       _c_source_match,
                       "Данные теряются на промежуточных слоях; «извлекли» ≠ «на экране»")
C_SOURCE_ISSUER = Check("fin.source_issuer", "Источники принадлежат эмитенту", Severity.HARD,
                        _c_source_issuer,
                        "Поиск отдаёт чужого эмитента: Роснефть→РуссНефть, Акрон→Сбер")
C_FRESHNESS = Check("fin.freshness", "Отчётность не протухла", Severity.SOFT,
                    _c_freshness, "Сквозная боль: устаревшие входные данные")
C_RETURN_UNITS = Check("fin.return_units", "Рентабельности в процентах", Severity.HARD,
                       _c_return_units, "Смешанные единицы roe/roa/ros")
# Две проверки на одной арифметике, но с РАЗНОЙ тяжестью: ошибка знака законной
# причины не имеет, а необъяснённый разрыв — вполне (прекращённая деятельность,
# доля неконтролирующих). Складывать их в одну severity значит либо простить
# первое, либо наказать за второе.
C_TAX_SIGN = Check("fin.tax_sign", "Знак чистой прибыли не перевёрнут", Severity.HARD,
                   _c_tax_sign, "IRKT-2022: величина сходится, знак противоположный")
C_TAX_IDENTITY = Check("fin.tax_identity", "Прибыль до налога + налог = чистая прибыль",
                       Severity.SOFT, _c_tax_identity,
                       "BLNG: одно битое поле при верном остальном файле")
C_ADJ_BRIDGE = Check("fin.adjusted_bridge", "Отчётная прибыль сходится с мостом нормализации",
                     Severity.HARD, _c_adjusted_bridge,
                     "BLNG: reported +190 млн при мосте, дающем −491 млн")
C_CROSS_TAB = Check("fin.cross_tab", "Вкладки не противоречат числам", Severity.SOFT,
                    _c_cross_tab, "Системный вывод аудита: платформа ломается на стыках")

CHECKS: list[Check] = [C_ARITHMETIC, C_PROFIT_VS_REVENUE, C_SOURCE_MATCH,
                       C_SOURCE_ISSUER, C_FRESHNESS, C_RETURN_UNITS,
                       C_TAX_SIGN, C_TAX_IDENTITY, C_ADJ_BRIDGE, C_CROSS_TAB]

# Версия набора: меняется при добавлении/изменении проверок. Прогоны с разными
# версиями сравнивать НЕЛЬЗЯ — иначе «качество выросло» окажется «проверок стало меньше».
CHECKS_VERSION = "fin-1.6"  # 1.6: установлена ли виновная сторона  # 1.3: пропуск-норма (банк вне «выручки») не режет покрытие
