"""Генератор `config/share_classes.json` — реестр КЛАССОВ АКЦИЙ по эмитентам.

🔴 ЗАЧЕМ. P/E, P/B, P/S — это (капитализация ЭМИТЕНТА) / (прибыль, капитал, выручка
ЭМИТЕНТА). Числитель всегда про всю компанию, значит и капитализация должна быть по
ВСЕМ классам акций. На бою это правило нарушалось у 69 тикеров из 264: аналитик брал
выпуск ОДНОГО класса. Примеры искажения (во столько раз занижена капитализация, а
значит и P/E, и P/B):

    KCHEP ×319   LSNGP ×92   BSPBP ×23   MTLRP ×4.0   SNGS ×1.22   TATN ×1.07

Отдельно — классы, которых на бирже НЕТ ВООБЩЕ и которых поэтому нет ни в `rates.csv`,
ни в MOEX ISS (проверено: ISS не отдаёт нелистингованные выпуски даже с is_trading=0).
Их приходится вести вручную, с источником:

    TRNFP — 569 446 800 обыкновенных у Росимущества (73% капитала!) вне биржи;
            торгуется только преф → капитализация занижена в 4,66 раза, P/E 0,96.
    RNFT  — 98 032 000 префов вне биржи, весь дивидендный поток идёт им.

Листингованные классы группируются по MOEX-полю EMITENTCAPITALIZATION: оно одинаково
у всех бумаг одного эмитента и равно СУММЕ их SECURITYCAPITALIZATION (сверено:
SBER 7 022 018 + SBERP 325 400 = 7 347 418 млн ₽). Это надёжнее склейки по имени
тикера «X + P»: она дала бы ложную пару, появись на бирже бумага с тикером-префиксом.

Запуск (разово, после обновления rates.csv):
    cd backend && venv/bin/python scripts/build_share_classes.py
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
RATES = BASE / "data" / "rates.csv"
# 🔴 backend/config, а НЕ корневой config/: Dockerfile собирается из контекста
# backend/ (WORKDIR /app + COPY . . + uvicorn app.main:app), поэтому корневой
# каталог config/ в образ не попадает и реестр там молча не читался бы.
OUT = BASE / "config" / "share_classes.json"

# ── Классы БЕЗ листинга: в rates.csv/ISS их нет, ведём руками ──────────────────
# valuation: how_priced — по какой цене оценивать неторгуемый класс.
#   "reference_class" — по цене торгуемого класса. Годится, когда экономика классов
#   сопоставима (у Транснефти дивиденд на обыкновенную и привилегированную РАВНЫЙ,
#   поэтому рынок и аналитики считают капитализацию именно так, ~1 трлн ₽, а не 216 млрд).
UNLISTED = {
    "TRNFP": {
        "unlisted": [{
            "class": "обыкновенные",
            "count": 569_446_800,
            "how_priced": "reference_class",
            "holder": "Росимущество (100%)",
        }],
        "note": "Уставный капитал 724 934 300 акций: 569 446 800 обыкновенных + "
                "155 487 500 привилегированных (после дробления 1:100 в феврале 2024). "
                "На бирже торгуются ТОЛЬКО привилегированные. Дивиденд на все классы "
                "равный, поэтому обыкновенные оцениваем по цене префа.",
        "source": "Устав ПАО «Транснефть»; структура акционерного капитала эмитента; "
                  "подтверждено ключевыми фактами в companies/TRNFP/financials.json",
    },
    # Один класс, но число акций в financials.json устарело: аналитик считал по
    # 6,62 млрд обыкновенных (до конвертации), а госпрефы типов А и Б (21,4 трлн и
    # 3,1 трлн шт) конвертированы в 6,3 млрд обыкновенных — операция завершена
    # 29.04.2026, и в rates.csv уже верные 12 927 766 416. verified_shares говорит
    # сервису: расхождение здесь — устаревшая цифра, а не выбор аналитика, правь.
    "VTBR": {
        "unlisted": [],
        "verified_shares": True,
        "note": "После конвертации привилегированных акций первого и второго типа "
                "(завершена 29.04.2026) у ВТБ 12,93 млрд обыкновенных акций номиналом "
                "50 ₽; привилегированных больше нет. Коэффициент конвертации — по "
                "средневзвешенной цене обыкновенной акции за 2025 год (82,67 ₽).",
        "source": "Сообщение ВТБ о завершении конвертации (апрель 2026); ISSUESIZE rates.csv",
    },
    "RNFT": {
        "unlisted": [{
            "class": "привилегированные",
            "count": 98_032_000,
            "how_priced": "reference_class",
            "holder": "структуры ВТБ / основного акционера",
        }],
        "note": "Уставный капитал 392 152 000 акций: 294 120 000 обыкновенных (торгуются) "
                "+ 98 032 000 привилегированных (на бирже НЕ обращаются). Весь дивидендный "
                "поток компании идёт на префы, по обыкновенным выплат нет с IPO-2016 — "
                "оценка префов по цене обыкновенной является ДОПУЩЕНИЕМ (скорее занижает "
                "их стоимость), поэтому пометка reliability=low.",
        "source": "Раскрытие ПАО НК «РуссНефть»; companies/RNFT/financials.json key_facts",
        "reliability": "low",
    },
}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> None:
    raw = RATES.read_text(encoding="cp1251").splitlines()
    head = next(i for i, l in enumerate(raw) if l.startswith("SECID;"))
    rows = list(csv.DictReader(io.StringIO("\n".join(raw[head:])), delimiter=";"))

    # группировка листингованных классов по эмитенту
    by_issuer: dict[str, list[dict]] = {}
    for r in rows:
        key = r.get("EMITENTCAPITALIZATION") or ""
        size = _f(r.get("ISSUESIZE"))
        if not key or not size:
            continue
        # цена класса на дату снапшота MOEX — резерв, когда по классу нет живой
        # котировки в quotes (у неликвидных префов её может не быть). Класс молча
        # выбросить нельзя: это снова занизит капитализацию — ровно тот баг, что чиним.
        sec_cap = _f(r.get("SECURITYCAPITALIZATION"))
        by_issuer.setdefault(key, []).append({
            "ticker": r["SECID"],
            "count": int(size),
            "listed": True,
            "type": "преф" if r["SECID"].endswith("P") and any(
                o["SECID"] == r["SECID"][:-1] for o in rows) else "обыкновенные",
            "snapshot_price": round(sec_cap / size, 6) if sec_cap else None,
        })

    out: dict[str, dict] = {}
    for classes in by_issuer.values():
        classes.sort(key=lambda c: (c["type"] != "обыкновенные", c["ticker"]))
        total_listed = sum(c["count"] for c in classes)
        for c in classes:
            entry = {
                "classes": classes,
                "total_listed_shares": total_listed,
                "total_shares": total_listed,
            }
            man = UNLISTED.get(c["ticker"])
            if man:
                unl = [{**u, "listed": False} for u in man["unlisted"]]
                # тип торгуемого класса выводим от ручной записи: у TRNFP пары «TRNF»
                # на бирже нет, и склейка по суффиксу «P» типа не определяет
                if any(u["class"] == "обыкновенные" for u in unl):
                    c = {**c, "type": "преф"}
                    classes = [c if x["ticker"] == c["ticker"] else x for x in classes]
                entry["classes"] = classes + unl
                entry["total_shares"] = total_listed + sum(u["count"] for u in unl)
                entry["note"] = man["note"]
                entry["source"] = man["source"]
                if man.get("verified_shares"):
                    entry["verified_shares"] = True
                if man.get("reliability"):
                    entry["reliability"] = man["reliability"]
            out[c["ticker"]] = entry

    # тикеры с ручной записью, которых не оказалось в rates (страховка от опечатки)
    missing = [t for t in UNLISTED if t not in out]
    if missing:
        raise SystemExit(f"В rates.csv нет тикеров из ручного реестра: {missing}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_doc": "Классы акций эмитентов. Листингованные — сгенерированы из rates.csv "
                "по группировке EMITENTCAPITALIZATION; нелистингованные — ручной реестр "
                "в scripts/build_share_classes.py (там же источники). Используется "
                "app/services/share_capital.py для расчёта капитализации ЭМИТЕНТА.",
        "_generated_by": "backend/scripts/build_share_classes.py",
        "issuers": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    multi = {t: e for t, e in out.items() if len(e["classes"]) > 1}
    print(f"тикеров: {len(out)}; из них с несколькими классами: {len(multi)}")
    for t in ("TRNFP", "RNFT", "SBER", "TATNP", "BSPBP"):
        if t in out:
            e = out[t]
            print(f"  {t:6} всего {e['total_shares']:>16,} "
                  f"(листинг {e['total_listed_shares']:>16,}) "
                  f"классы: {', '.join(c.get('ticker') or c['class'] for c in e['classes'])}")


if __name__ == "__main__":
    main()
