"""Ремонт worklist раскатки «доходность за риск» из почищенной БД облигаций.

Зачем: risk_worklist.json — статический срез, отставший от модели Bond. По мере
спуска по спреду в него попал вал бумаг, где системный спред/YTM — АРТЕФАКТ, а не
премия за риск: флоатеры (G-спред к фикс-ОФЗ бессмыслен), near-maturity/near-offer
(YTM раздут коротким хвостом), и «нет рейтинга» там, где рейтинг эмитента есть
(пропагация по сериям). Скрипт обогащает каждую запись фактами из БД и помечает
артефакты, чтобы селектор раскатки брал РЕАЛЬНЫЕ кандидаты «доходность за риск»,
а не технический шум.

Запуск (из backend):  venv/bin/python -m scripts.repair_worklist
Перед записью делает .bak. Идемпотентно.
"""
import json
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.bond import Bond

WORKLIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "bond_issuers", "_worklog", "risk_worklist.json")


def _days_to(d) -> int | None:
    if not d:
        return None
    return (d - date.today()).days


def main() -> None:
    with open(WORKLIST, encoding="utf-8") as f:
        wl = json.load(f)

    db = SessionLocal()
    try:
        bonds = {b.secid: b for b in db.query(Bond).all()}
    finally:
        db.close()

    matched = artifacts = rating_filled = 0
    for e in wl:
        b = bonds.get(e.get("secid"))
        if b is None:
            e.setdefault("artifact", None)        # не найдена в БД — судить не можем
            e.setdefault("coupon_type", None)
            continue
        matched += 1
        # ── тип купона / амортизация ──
        e["coupon_type"] = b.coupon_type
        e["has_amortization"] = bool(b.has_amortization)
        # ── near-maturity / near-offer (ближайшее из оферты/погашения ≤120 дн) ──
        tails = [d for d in (_days_to(b.offer_date), _days_to(b.maturity_date)) if d is not None]
        d_near = min(tails) if tails else None
        e["days_to_event"] = d_near
        near = d_near is not None and 0 <= d_near <= 120
        e["near_offer"] = bool(near)
        # ── рейтинг (после пропагации по эмитенту) ──
        if b.agency_rating:
            if e.get("rating") != b.agency_rating:
                rating_filled += 1
            e["rating"] = b.agency_rating
        # ── чистый спред: G-спред осмыслен только для фикс-купона вне near-зоны ──
        is_float = b.coupon_type in ("floater", "linker", "structured")
        e["ytm"] = float(b.ytm) if b.ytm is not None else e.get("ytm")
        if is_float or near:
            e["clean_spread"] = None
            e["spread"] = None                    # артефактный спред больше не вводит в заблуждение
        else:
            e["clean_spread"] = b.spread_bp
            e["spread"] = b.spread_bp
        e["floater_spread_bp"] = b.floater_spread_bp
        # ── артефакт: спред/YTM нельзя сравнивать со светофором группы ──
        e["artifact"] = bool(is_float or near)
        if e["artifact"]:
            artifacts += 1

    shutil.copy(WORKLIST, WORKLIST + ".bak")
    with open(WORKLIST, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

    base = os.path.dirname(os.path.dirname(WORKLIST))  # bond_issuers/

    def has_md(slug):
        return bool(slug) and os.path.exists(os.path.join(base, slug, "risk.md"))

    done = sum(1 for e in wl if has_md(e.get("slug")))
    clean_undone = sum(1 for e in wl if not e.get("artifact") and not has_md(e.get("slug")))
    print(f"записей: {len(wl)}, сопоставлено с БД: {matched}")
    print(f"помечено артефактов (флоатер/near): {artifacts}")
    print(f"рейтинг дополнен из БД: {rating_filled}")
    print(f"разборов готово (risk.md): {done}")
    print(f"осталось ЧИСТЫХ (не-артефакт) эмитентов без разбора: {clean_undone}")


if __name__ == "__main__":
    main()
