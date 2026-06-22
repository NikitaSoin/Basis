"""LLM-извлечение долей бизнес-сегментов из business_model.md → financials.json["segments"]
(структурированные числа под бары вкладки «Бизнес-модель»). Разовый идемпотентный проход.

Идемпотентность/resume: пропускаем компанию, если ключ "segments" уже есть (в т.ч. []).
[] = обработано, сегментации нет (моносегмент/не раскрыто) → фронт покажет прозу.

Запуск (из backend, с .env):  python -m scripts.extract_bm_segments_llm
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from app.services import llm

COMPANIES = Path(__file__).resolve().parent.parent / "companies"

SYS = ("Ты — финансовый аналитик. Извлекаешь структуру выручки по БИЗНЕС-СЕГМЕНТАМ "
       "(направлениям/бизнес-юнитам) компании из текста разбора. Отвечаешь строго JSON.")


def make_prompt(name, ticker, md):
    return (
        f"Разбор бизнес-модели компании {name} ({ticker}):\n\n{md[:12000]}\n\n"
        "Извлеки БИЗНЕС-СЕГМЕНТЫ (направления/бизнес-юниты) и их доли в ВЫРУЧКЕ. "
        'Верни строго JSON: {"segments":[{"name":"...","pct":<число>,"note":"<короткая фраза-факт или пусто>"}]}. '
        "Правила: только бизнес-сегменты (НЕ география, НЕ статьи расходов, НЕ баланс/активы). "
        "pct — процент выручки числом без знака %. Если доля дана диапазоном — возьми среднее. "
        'Если компания моносегментная или разбивки выручки в тексте нет — верни {"segments":[]}. '
        "Не выдумывай доли, которых нет в тексте. note — 1 короткая фраза (ключевой факт) или пусто."
    )


def clean(segs):
    out = []
    for s in segs or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        try:
            pct = float(s.get("pct"))
        except (TypeError, ValueError):
            continue
        if not name or not (0 < pct <= 100):
            continue
        note = str(s.get("note") or "").strip()[:180]
        item = {"name": name[:90], "pct": round(pct, 1)}
        if note:
            item["note"] = note
        out.append(item)
    return out[:8]


def main():
    dirs = sorted(d for d in COMPANIES.iterdir()
                  if (d / "business_model.md").exists() and (d / "financials.json").exists())
    done = skip = seg = mono = err = 0
    print(f"Компаний к обработке: {len(dirs)}", flush=True)
    for d in dirs:
        fj = d / "financials.json"
        try:
            data = json.loads(fj.read_text(encoding="utf-8"))
        except Exception:
            err += 1
            continue
        if "segments" in data:
            skip += 1
            continue
        md = (d / "business_model.md").read_text(encoding="utf-8")
        name = (data.get("meta") or {}).get("name") or d.name
        try:
            r = llm.complete(SYS, make_prompt(name, d.name, md), json_mode=True)
            segs = clean(r.get("segments") if isinstance(r, dict) else None)
        except Exception as e:
            print(f"ERR {d.name}: {str(e)[:140]}", flush=True)
            err += 1
            time.sleep(1.0)
            continue
        data["segments"] = segs
        fj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        done += 1
        if len(segs) >= 2:
            seg += 1
        else:
            mono += 1
        if done % 20 == 0:
            print(f"...{done} обработано (с сегментами≥2: {seg})", flush=True)
        time.sleep(0.25)
    print(f"ГОТОВО: обработано {done}, пропущено(уже было) {skip}, "
          f"с сегментами≥2 {seg}, моно/нет {mono}, ошибок {err}", flush=True)


if __name__ == "__main__":
    main()
