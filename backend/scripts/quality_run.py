#!/usr/bin/env python3
"""Прогон качества пайплайна: проверки по всем карточкам + эталонный набор.

    python3 backend/scripts/quality_run.py --pipeline financials
    python3 backend/scripts/quality_run.py --golden-only
    python3 backend/scripts/quality_run.py --ticker SBER --verbose
    python3 backend/scripts/quality_run.py --history

🔴 Читать результат так: сначала coverage, потом score. Score при низком
покрытии ничего не значит — прогон помечается «НЕДЕЙСТВИТЕЛЕН».
"""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.quality import golden as golden_mod          # noqa: E402
from app.services.quality import runner                        # noqa: E402
from app.services.quality.contract import Status               # noqa: E402

ARTIFACTS = ROOT / "quality" / "runs"


def print_golden(g: dict) -> None:
    mark = "✓" if not g["failed"] else "✕"
    print(f"\nЭТАЛОННЫЙ НАБОР: {mark} {g['passed']}/{g['total']}")
    for r in g["results"]:
        sign = "✓" if r["passed"] else "✕"
        print(f"  {sign} {r['case']:12} {r.get('check_id', ''):22} {r.get('title', '')}")
        if not r["passed"] or r.get("kind") == "mutation":
            print(f"      {r['detail']}")


def print_run(res) -> None:
    print(f"\nПРОГОН «{res.pipeline}» · набор {res.checks_version} · субъектов {res.subjects}")
    print(f"{'проверка':24} {'ok':>5} {'fail':>5} {'skip':>5} {'покрытие':>9} {'доля брака':>11}")
    for check_id, s in res.per_check.items():
        if check_id.startswith("_"):
            continue
        fr = "—" if s["fail_rate"] is None else f"{s['fail_rate']:.1%}"
        print(f"{check_id:24} {s['ok']:5} {s['fail']:5} {s['skip']:5} "
              f"{s['coverage']:8.1%} {fr:>11}")
    unread = res.per_check.get("_unreadable_cards")
    if unread:
        print(f"{'нечитаемые карточки':24} {unread['count']:5}")
    print(f"\n  ПОКРЫТИЕ  {res.coverage:.1%}   (доля субъектов, где проверки реально отработали)")
    if res.valid:
        print(f"  КАЧЕСТВО  {res.score:.1%}   (карточек без грубых находок)")
        print(f"  МЯГКИЕ    {res.soft_rate:.1%}   (ещё столько — с замечаниями)")
    else:
        print(f"  🔴 ПРОГОН НЕДЕЙСТВИТЕЛЕН: {res.invalid_reason}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", default="financials")
    ap.add_argument("--ticker", action="append", help="ограничить прогон тикерами")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--golden-only", action="store_true", help="только эталонный набор")
    ap.add_argument("--no-golden", action="store_true")
    ap.add_argument("--no-db", action="store_true", help="не писать в реестр")
    ap.add_argument("--note", default="")
    ap.add_argument("--verbose", action="store_true", help="показать сами находки")
    ap.add_argument("--history", action="store_true", help="показать прошлые прогоны и выйти")
    args = ap.parse_args()

    if args.history:
        return show_history(args.pipeline)

    g = None
    if not args.no_golden:
        g = golden_mod.run_golden(date.today().year)
        print_golden(g)
    if args.golden_only:
        return 0 if g and not g["failed"] else 1

    res = runner.run(args.pipeline, limit=args.limit, only=args.ticker)
    res.golden = g
    print_run(res)

    if args.verbose:
        print("\nНАХОДКИ:")
        for o in res.outcomes:
            if o.status is Status.FAIL:
                print(f"  [{o.severity.value}] {o.subject:7} {o.check_id:24} {o.message}")

    path = runner.write_artifact(res, ARTIFACTS)
    print(f"\nартефакт: {path.relative_to(ROOT.parent)}")
    if not args.no_db:
        run_id = runner.persist(res, triggered_by="cli", note=args.note)
        print(f"реестр: {'прогон #' + str(run_id) if run_id else 'БД недоступна — только артефакт'}")

    ok = res.valid and (g is None or not g["failed"])
    return 0 if ok else 1


def show_history(pipeline: str) -> int:
    try:
        from sqlalchemy import select
        from app.db.session import SessionLocal
        from app.models.quality_run import QualityRun
    except Exception as exc:
        print(f"БД недоступна: {exc}")
        return 1
    with SessionLocal() as db:
        rows = db.execute(select(QualityRun).where(QualityRun.pipeline == pipeline)
                          .order_by(QualityRun.started_at.desc()).limit(20)).scalars().all()
    if not rows:
        print("прогонов ещё не было")
        return 0
    print(f"{'id':>4} {'когда':17} {'набор':9} {'субъектов':>9} {'покрытие':>9} "
          f"{'качество':>9} {'эталон':>8}")
    for r in rows:
        when = r.started_at.strftime("%d.%m %H:%M")
        score = "—" if not r.valid else f"{float(r.score):.1%}"
        gold = "—" if r.golden_total is None else f"{r.golden_passed}/{r.golden_total}"
        print(f"{r.id:>4} {when:17} {r.checks_version:9} {r.subjects:9} "
              f"{float(r.coverage or 0):8.1%} {score:>9} {gold:>8}")
    print("\n🔴 сравнивать между собой можно только прогоны с ОДИНАКОВЫМ набором проверок")
    return 0


if __name__ == "__main__":
    sys.exit(main())
