"""Капитализация ЭМИТЕНТА — по всем классам акций, а не по одной торгуемой бумаге.

🔴 БАГ, КОТОРЫЙ ЭТО ЧИНИТ. P/E = капитализация / прибыль, P/B = капитализация /
капитал. Числитель — про всю компанию, значит и капитализация должна быть по ВСЕМ
классам. На бою правило нарушалось у 69 тикеров из 264: в `meta.shares_outstanding`
лежал выпуск ОДНОГО класса, и мультипликаторы выходили заниженными в разы:

    TRNFP  P/E 0,96 и P/B 0,07 — торгуется только преф (155,5 млн), а обыкновенных
           569,4 млн у Росимущества вне биржи ⇒ капитализация занижена в 4,66 раза;
    VTBR   P/E 1,03 — взято 6,62 млрд обыкновенных, тогда как после конвертации
           префов (завершена 29.04.2026) их 12,93 млрд ⇒ занижение вдвое;
    BSPBP  ×23, LSNGP ×92, KCHEP ×319 — то же самое на префах региональных эмитентов.

Дальше ошибка расходилась по всей платформе, потому что P/B — вход и для BFV
(`bfv/params.py` берёт BVPS как цена / P/B), и для прикидки run-rate (`run_rate.py`
выводит из P/B число акций). Поэтому чинить надо ОДНО число — капитализацию, — и
остальное выправляется само.

КАК СЧИТАЕМ. Живая капитализация = Σ по классам (число акций × цена класса):
живая котировка класса из `quotes`, а если её нет (неликвидный преф) — цена снапшота
MOEX из реестра, сдвинутая на то же движение, что у основного класса. Класс молча
выбросить нельзя: это ровно то занижение, которое чиним. Нелистингованные классы —
из реестра `config/share_classes.json` (там же источник по каждому), оцениваются по
цене торгуемого класса; допущение честно помечается.

ЧЕГО СЕРВИС НЕ ДЕЛАЕТ. Не трогает числитель (прибыль/капитал — работа аналитика) и не
«улучшает» оценку: только приводит знаменатель к правилу, которое платформа сама и
декларирует (`.claude/agents/financial-analyst.md`, раздел про префы).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "share_classes.json"
_CACHE: dict = {"data": None}

# 🔴 ОТ ЧЕГО СЧИТАЛ АНАЛИТИК — ВОССТАНАВЛИВАЕМ, А НЕ УГАДЫВАЕМ.
# Первая версия масштабировала мультипликаторы по числу акций из meta и на BSPBP
# выдала P/B 15,4 вместо 0,6 — потому что там P/B был записан как «цена ÷ BVPS»
# (число акций внутри уже сократилось), и множитель по классам применился второй раз.
# Опора надёжнее: mcap_аналитика = P/B × капитал. Капитал — обычная балансовая
# статья, не нормализованная, поэтому равенство верно при ЛЮБОЙ базе, которую
# выбрал аналитик. Дальше все мультипликаторы двигаем одним коэффициентом
# mcap_живая / mcap_аналитика — это сохраняет его нормализацию прибыли (P/E мог
# считаться по adjusted) и приводит к общему знаменателю и P/E, и P/B, и P/S.
_UNITS = {"млн": 1e6, "млрд": 1e9, "тыс": 1e3, "тысячи": 1e3, "тыс. руб.": 1e3}
# k вне этого коридора = сохранённые числа несогласованы между собой (иная база
# капитала, опечатка в единицах). Тогда честнее не трогать, чем «поправить» наугад.
_K_MIN, _K_MAX = 0.1, 50.0


def _registry() -> dict:
    if _CACHE["data"] is None:
        try:
            _CACHE["data"] = json.loads(_CONFIG.read_text(encoding="utf-8")).get("issuers") or {}
        except Exception:  # noqa: BLE001 — без реестра просто работаем как раньше
            logger.warning("share_classes.json недоступен — капитализация по одному классу")
            _CACHE["data"] = {}
    return _CACHE["data"]


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _live_prices(db: Session, tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    try:
        rows = db.execute(text(
            "SELECT DISTINCT ON (c.ticker) c.ticker, q.close FROM quotes q "
            "JOIN companies c ON c.id = q.company_id "
            "WHERE c.ticker = ANY(:ts) AND q.close IS NOT NULL "
            "ORDER BY c.ticker, q.date DESC"), {"ts": tickers}).all()
        return {t: float(p) for t, p in rows if p}
    except Exception:  # noqa: BLE001
        return {}


def apply_issuer_capital(db: Session, ticker: str, fin: dict) -> dict:
    """Привести multiples.current к капитализации ЭМИТЕНТА. Мутирует и возвращает fin.

    🔴 Зовётся ВСЕМИ потребителями `financials.json`, а не только витриной вкладки:
    BFV (`bfv/service.py`) и прикидка (`run_rate.py`) читают файл с диска напрямую и
    выводят из P/B и BVPS, и число акций — без этого шага они продолжали бы считать
    от капитализации одного класса (у TRNFP это давало справедливую цену в разы выше).
    Ошибок наружу не выпускает: не смогли — оставили как было."""
    try:
        cap = issuer_capital(db, ticker, fin)
    except Exception:  # noqa: BLE001
        cap = None
    if not cap:
        return fin
    from app.services.live_multiples import live_scale_multiples
    fin.setdefault("multiples", {})["current"] = live_scale_multiples(
        fin, cap["mcap_live"], cap["shares_used"])

    # BVPS — тоже на ПОЛНОЕ число акций. Без этого поправка до BFV не доходит:
    # он берёт готовый balance_sheet.book_value_per_share и только при его
    # отсутствии считает BVPS как цена/(P/B). У ВТБ сохранённый BVPS 412 ₽ посчитан
    # по 6,62 млрд акций (до конвертации префов), при 12,93 млрд он равен 211 ₽ —
    # вдвое. Правим ТОЛЬКО последнее значение ряда: только оно идёт в оценку, а
    # исторические точки считались по числу акций СВОИХ лет и верны как есть.
    equity = _equity_rub(fin)
    bvps_fair = equity / cap["total_shares"] if equity else None
    if bvps_fair:
        bs = fin.get("balance_sheet")
        series = bs.get("book_value_per_share") if isinstance(bs, dict) else None
        if isinstance(series, list):
            idx = next((i for i in range(len(series) - 1, -1, -1) if _num(series[i])), None)
            old = _num(series[idx]) if idx is not None else None
            if old and abs(bvps_fair / old - 1.0) > 0.05:
                series[idx] = round(bvps_fair, 2)
                cap["warnings"].append(
                    f"BVPS пересчитан на полное число акций: {old:,.0f} → {bvps_fair:,.0f} ₽"
                    .replace(",", " "))

    fin["multiples"]["capital_basis"] = {
        "basis": cap["basis"],
        "factor": round(cap["k"], 4),
        "total_shares": cap["total_shares"],
        "classes": cap["classes"],
        "reliability": cap.get("reliability"),
        "note": cap.get("note"),
        "source": cap.get("source"),
        "warnings": cap["warnings"],
    }
    return fin


def _equity_rub(fin: dict) -> float | None:
    """Балансовый капитал в РУБЛЯХ (в файле он в млн/млрд/тыс — приводим по meta.unit)."""
    bs = fin.get("balance_sheet") or {}
    src = (bs.get("total_equity") or (bs.get("equity") or {}).get("total_equity")
           or (fin.get("bank_balance") or {}).get("total_equity"))
    val = None
    if isinstance(src, list):
        for x in reversed(src):
            if _num(x) is not None:
                val = _num(x)
                break
    else:
        val = _num(src)
    if val is None or val <= 0:
        return None
    return val * _UNITS.get((fin.get("meta") or {}).get("unit"), 1e6)


def issuer_capital(db: Session, ticker: str, fin: dict,
                   prices: dict[str, float] | None = None) -> dict | None:
    """Капитализация эмитента по всем классам + база, от которой считал аналитик.

    Возврат (или None, если пересчитывать нечего/нечем):
      mcap_live     — живая капитализация ЭМИТЕНТА по всем классам, ₽
      mcap_analyst  — капитализация, заложенная в сохранённые мультипликаторы, ₽
      k             — отношение первого ко второму (движение цены + поправка классов)
      basis, classes, warnings, reliability
    """
    ticker = ticker.upper()
    entry = _registry().get(ticker)
    if not entry:
        return None
    meta = fin.get("meta") or {}
    frozen_price = _num(meta.get("last_price"))
    pb = _num(((fin.get("multiples") or {}).get("current") or {}).get("pb"))
    equity = _equity_rub(fin)
    if not (frozen_price and frozen_price > 0 and pb and pb > 0 and equity):
        return None
    mcap_analyst = pb * equity

    total = _num(entry.get("total_shares"))
    if not total:
        return None
    classes = entry.get("classes") or []

    # 🔴 ПРАВИМ ТОЛЬКО ОПОЗНАННОЕ. Восстановленная база аналитика должна совпасть
    # либо с полным выпуском (тогда всё и так верно), либо с выпуском КОНКРЕТНОГО
    # класса — это и есть доказательство, что класс забыли. Если она не бьётся ни с
    # чем (например, NNSB: 664 тыс. акций при классах 3,92 млн и 1,06 млн), значит
    # разъехалось что-то ещё — база капитала, единицы, — и «поправка» разнесёт чужую
    # ошибку дальше. Тогда молчим: у неверного числа не должно появляться уверенного вида.
    # Пробуем не только цену САМОЙ бумаги: у пар «обычка/преф» аналитик часто
    # копирует в файл префа мультипликаторы эмитента, посчитанные по цене обычки
    # (у MFGSP и MFGS записан один и тот же P/B 0,235). Тогда деление на цену префа
    # даёт бессмыслицу, а на цену обычки — ровно выпуск обыкновенных. Без этого
    # правился только один тикер пары, и бумаги одного эмитента разъезжались между
    # собой — то самое расхождение на стыках, ради которого всё и затевалось.
    near = lambda a, b: bool(a and b and abs(a / b - 1.0) < 0.12)  # noqa: E731
    cand_prices = [frozen_price] + [_num(c.get("snapshot_price")) for c in classes]
    counts = [total] + [_num(c.get("count")) for c in classes]
    recognised = bool(entry.get("verified_shares")) or any(
        near(mcap_analyst / p, n) for p in cand_prices if p and p > 0 for n in counts)
    if not recognised:
        return None
    listed = [c for c in classes if c.get("listed") and c.get("ticker")]
    # prices передаёт скринер: он и так грузит цены всей вселенной одним запросом,
    # а поштучный SELECT на 264 тикера положил бы бэк (тот же урок, что с батчем
    # справедливых цен в screener_scoring.py)
    if prices is None:
        prices = _live_prices(db, [c["ticker"] for c in listed])
    ref_live = prices.get(ticker)
    ref_snap = next((_num(c.get("snapshot_price")) for c in listed if c.get("ticker") == ticker), None)
    # движение цены с даты снапшота реестра — им же двигаем классы без живой котировки
    drift = (ref_live / ref_snap) if (ref_live and ref_snap and ref_snap > 0) else 1.0

    warnings: list[str] = []
    mcap = 0.0
    for c in listed:
        n = _num(c.get("count")) or 0.0
        p = prices.get(c["ticker"])
        if p is None:
            snap = _num(c.get("snapshot_price"))
            if snap:
                p = snap * drift
                if c["ticker"] != ticker:
                    warnings.append(f"по классу {c['ticker']} нет живой котировки — "
                                    "взята цена снапшота с поправкой на движение основного класса")
        if p:
            mcap += n * p
    ref_for_unlisted = ref_live or (ref_snap or 0.0)
    for c in classes:
        if c.get("listed"):
            continue
        n = _num(c.get("count")) or 0.0
        if c.get("how_priced") == "reference_class" and ref_for_unlisted:
            mcap += n * ref_for_unlisted
            warnings.append(f"класс «{c.get('class')}» ({n:,.0f} шт, {c.get('holder')}) на бирже "
                            "не обращается — оценён по цене торгуемого класса"
                            .replace(",", " "))
    if mcap <= 0:
        return None

    k = mcap / mcap_analyst
    if not (_K_MIN <= k <= _K_MAX):
        return None

    return {
        "mcap_live": mcap,
        "mcap_analyst": mcap_analyst,
        # live_scale_multiples сам считает базу как last_price × shares — передаём
        # ей ровно ту базу, что восстановили по P/B (в «акциях» этой базы)
        "shares_used": mcap_analyst / frozen_price,
        "total_shares": total,
        "k": k,
        "basis": ("капитализация эмитента по всем классам акций"
                  if len(classes) > 1 else "капитализация эмитента"),
        "classes": classes,
        "reliability": entry.get("reliability"),
        "note": entry.get("note"),
        "source": entry.get("source"),
        "warnings": warnings,
    }
