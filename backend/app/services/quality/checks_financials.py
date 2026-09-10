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
from app.services.quality.contract import Check, CheckOutcome, Severity, fail, ok, skip

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
        yield skip(C_PROFIT_VS_REVENUE, subject, "банк: строка «выручка» иная по смыслу")
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
                               f"первичка записана в единицах, отличных от объявленных: "
                               f"расхождение ×{power:,.0f} на {len(diffs)} из {compared} строк "
                               f"(meta первички говорит «{(ext.get('meta') or {}).get('unit')}»)",
                               kind="unit_mismatch", factor=power,
                               compared=compared, diffs=len(diffs))
                    return

    if diffs:
        line, y, av, bv, pct = max(diffs, key=lambda d: abs(d[4]))
        yield fail(C_SOURCE_MATCH, subject,
                   f"расходится с первичкой в {len(diffs)} из {compared} сверок; худшее — "
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
        f = hard[0]
        yield fail(C_CROSS_TAB, subject,
                   f"{len(hard)} расхождений прозы с financials.json; напр. {f.get('file')} "
                   f"{f.get('year') or ''} {f.get('metric')}: в тексте {f.get('in_text')} "
                   f"против {f.get('fact_bln')} в данных",
                   mismatches=len(hard), files=prose)
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
C_CROSS_TAB = Check("fin.cross_tab", "Вкладки не противоречат числам", Severity.SOFT,
                    _c_cross_tab, "Системный вывод аудита: платформа ломается на стыках")

CHECKS: list[Check] = [C_ARITHMETIC, C_PROFIT_VS_REVENUE, C_SOURCE_MATCH,
                       C_SOURCE_ISSUER, C_FRESHNESS, C_RETURN_UNITS, C_CROSS_TAB]

# Версия набора: меняется при добавлении/изменении проверок. Прогоны с разными
# версиями сравнивать НЕЛЬЗЯ — иначе «качество выросло» окажется «проверок стало меньше».
CHECKS_VERSION = "fin-1.2"  # 1.2: сверка стыков по payload + само-проба «сравнила ли она что-нибудь»
