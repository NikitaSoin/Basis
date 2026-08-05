"""Приёмка сводов «Обзора», заготовленных субагентами.

🔴 Зачем отдельная приёмка. Своды, собранные на бою, проходят код-гейт внутри сервиса.
Заготовки из файлов этот путь минуют — значит на них надо натравить ТОТ ЖЕ гейт, иначе
в репозиторий попадёт то, что боевой контур не пустил бы: выдуманные числа, советы
«купить», рассуждения о вкладке, разбора которой у компании нет.

Запуск:
    python scripts/accept_overview_synthesis.py            # проверить всё
    python scripts/accept_overview_synthesis.py --fix      # + удалить брак
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal                       # noqa: E402
from app.services.overview_synthesis import (                 # noqa: E402
    COMPANIES_DIR, SYNTHESIS_FILE, _fair_value, _gate, _tab_inputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true",
                        help="удалить файлы, не прошедшие гейт")
    args = parser.parse_args()

    db = SessionLocal()
    ok, bad, missing = [], [], []
    try:
        for d in sorted(COMPANIES_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            path = d / SYNTHESIS_FILE
            if not path.exists():
                missing.append(d.name)
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                bad.append((d.name, [f"нечитаемый JSON: {type(e).__name__}"]))
                continue
            notes = _gate(data, _tab_inputs(db, d.name), _fair_value(db, d.name), d.name)
            if notes:
                bad.append((d.name, notes))
                if args.fix:
                    path.unlink()
            else:
                ok.append(d.name)
    finally:
        db.close()

    print(f"принято: {len(ok)} | брак: {len(bad)} | нет файла: {len(missing)}")
    for ticker, notes in bad[:40]:
        print(f"  ✗ {ticker}: {notes[:3]}")
    if missing[:1]:
        print(f"  без свода (первые 15): {missing[:15]}")
    return 1 if bad and not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
