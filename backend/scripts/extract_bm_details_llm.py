"""LLM-извлечение деталей бизнес-модели → financials.json: cost_breakdown (постатейные
расходы ДО EBITDA, % выручки, тип переменная/постоянная), key_facts (ключевые факты для
секции «Описание»), geo_split (доли выручки по географии, если раскрыты). Источник —
business_model.md. Разовый идемпотентный проход (как сегменты).

Resume: пропускаем компанию, если ключ "cost_breakdown" уже есть.
Сумма cost_breakdown ориентируется на (100 − маржа EBITDA) из financials (расходы до EBITDA).

Запуск (из backend, с .env):  python -m scripts.extract_bm_details_llm
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

SYS = ("Ты — финансовый аналитик. Из текста разбора бизнес-модели извлекаешь структуру в JSON: "
       "ключевые факты о компании, постатейную структуру расходов ДО EBITDA и доли выручки по "
       "географии. Отвечаешь строго JSON, ничего не выдумываешь сверх текста.")


def make_prompt(name, ticker, md, exp_target):
    tgt = f"~{exp_target:.0f}% выручки" if exp_target else "сумму из текста"
    return (
        f"Разбор бизнес-модели компании {name} ({ticker}):\n\n{md[:13000]}\n\n"
        "Верни строго JSON со схемой:\n"
        '{"key_facts":[{"label":"...","value":"..."}],'
        '"cost_breakdown":[{"name":"...","pct":<число>,"type":"variable"|"fixed"}],'
        '"geo_split":[{"region":"...","pct":<число>}]}\n'
        "Правила:\n"
        "- key_facts: 3–6 коротких фактов (собственник/контроль, доля государства или доля рынка, "
        "типы акций (об./прив.), штаб/регион, суть модели). value — короткая фраза.\n"
        f"- cost_breakdown: расходы ДО EBITDA по статьям (производственные налоги, закупка сырья, "
        f"опекс, транспорт, коммерческие/админ. и т.п.), каждая как % ВЫРУЧКИ числом без %. "
        f"Сумма статей должна примерно равняться {tgt} (это доля расходов до EBITDA). "
        "type: variable (сжимается с выручкой — сырьё, производств. налоги) или fixed (постоянные/"
        "разовые — амортизация сюда НЕ включать, она после EBITDA). Если детализации в тексте нет — [].\n"
        "- geo_split: доли выручки по рынкам (напр. Внутренний рынок РФ / Экспорт), % числом. "
        "Если долей в тексте нет — [].\n"
        "Не выдумывай числа, которых нет в тексте; где не уверен — опускай статью."
    )


def clean_costs(items, exp_target):
    out = []
    for s in items or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        try:
            pct = float(s.get("pct"))
        except (TypeError, ValueError):
            continue
        if not name or not (0 < pct <= 100):
            continue
        typ = "fixed" if str(s.get("type") or "").lower().startswith("fix") else "variable"
        out.append({"name": name[:70], "pct": round(pct, 1), "type": typ})
    return out[:8]


def clean_facts(items):
    out = []
    for s in items or []:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "").strip()
        value = str(s.get("value") or "").strip()
        if label and value:
            out.append({"label": label[:40], "value": value[:120]})
    return out[:6]


def clean_geo(items):
    out = []
    for s in items or []:
        if not isinstance(s, dict):
            continue
        region = str(s.get("region") or "").strip()
        try:
            pct = float(s.get("pct"))
        except (TypeError, ValueError):
            continue
        if region and 0 < pct <= 100:
            out.append({"region": region[:50], "pct": round(pct, 1)})
    return out[:6]


def main():
    dirs = sorted(d for d in COMPANIES.iterdir()
                  if (d / "business_model.md").exists() and (d / "financials.json").exists())
    done = skip = err = 0
    cb = kf = gs = 0
    print(f"Компаний к обработке: {len(dirs)}", flush=True)
    for d in dirs:
        fj = d / "financials.json"
        try:
            data = json.loads(fj.read_text(encoding="utf-8"))
        except Exception:
            err += 1
            continue
        if "cost_breakdown" in data:
            skip += 1
            continue
        # целевая доля расходов до EBITDA = 100 − маржа EBITDA (последний год)
        isx = data.get("income_statement") or {}
        rev = (isx.get("revenue") or [None])[-1]
        eb = (isx.get("ebitda") or [None])[-1]
        exp_target = (100 - eb / rev * 100) if (rev and eb is not None) else None
        md = (d / "business_model.md").read_text(encoding="utf-8")
        name = (data.get("meta") or {}).get("name") or d.name
        try:
            r = llm.complete(SYS, make_prompt(name, d.name, md, exp_target), json_mode=True)
            r = r if isinstance(r, dict) else {}
            data["cost_breakdown"] = clean_costs(r.get("cost_breakdown"), exp_target)
            data["key_facts"] = clean_facts(r.get("key_facts"))
            data["geo_split"] = clean_geo(r.get("geo_split"))
        except Exception as e:
            print(f"ERR {d.name}: {str(e)[:140]}", flush=True)
            err += 1
            time.sleep(1.0)
            continue
        fj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        done += 1
        cb += len(data["cost_breakdown"]) >= 2
        kf += len(data["key_facts"]) >= 1
        gs += len(data["geo_split"]) >= 1
        if done % 20 == 0:
            print(f"...{done} (cost≥2:{cb} facts:{kf} geo:{gs})", flush=True)
        time.sleep(0.25)
    print(f"ГОТОВО: обработано {done}, пропущено {skip}, ошибок {err}; "
          f"cost≥2 {cb}, key_facts {kf}, geo {gs}", flush=True)


if __name__ == "__main__":
    main()
