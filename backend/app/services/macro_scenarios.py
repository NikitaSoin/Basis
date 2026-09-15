"""Расчётный модуль макросценариев карточки компании (пилот, v1).

Методика владельца: docs/Макроэкономика_Финансовая_модель_v1.md (0.2 «коэффициент как объект»,
7.2, Часть 9 модификаторы, 10.2–10.4) и docs/Описание_вкладки_макроэкономика.md (Часть 4:
расчёт линейный, без лагов, от фактического результата года; 0.5: агент не считает арифметику).
Контракт файлов: docs/macro_model_contract_v1.md.

Разделение труда: агент-модельер задаёт объекты коэффициентов и модификаторы
(companies/<T>/macro_model.json), сценарии регулятора лежат централизованно
(config/cbr_scenarios.json), ЗДЕСЬ — вся арифметика. Результат — companies/<T>/macro_scenarios.json.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = ROOT / "config" / "cbr_scenarios.json"
COMPANIES_DIR = ROOT / "companies"

LINES = ("revenue", "ebitda", "net_profit")
LINE_LABELS = {"revenue": "выручка", "ebitda": "EBITDA", "net_profit": "чистая прибыль"}

# «Заметное изменение» переменной для числовых привязок факторов (блок 2 вкладки).
# ("abs", x) — на x единиц; ("rel", r) — на r × значение базового периода.
STEPS: dict[str, tuple[str, float]] = {
    "usdrub_avg": ("rel", 0.10), "key_rate_avg": ("abs", 1.0), "oil_tax_price": ("abs", 10.0),
    "gdp": ("abs", 1.0), "inflation_avg": ("abs", 1.0), "inflation_dec": ("abs", 1.0),
    "real_wage": ("abs", 1.0), "nominal_wage": ("abs", 1.0), "unemployment": ("abs", 1.0),
    "consumption_hh": ("abs", 1.0), "gfcf": ("abs", 1.0), "exports_vol": ("abs", 1.0),
    "imports_vol": ("abs", 1.0), "credit_total": ("abs", 5.0), "credit_corp": ("abs", 5.0),
    "credit_hh": ("abs", 5.0), "mortgage": ("abs", 5.0), "money_supply": ("abs", 5.0),
    "current_account": ("abs", 10.0),
}
DEFAULT_STEP = ("rel", 0.10)
LINEARITY_LIMIT_PCT = 40.0  # дальше линейный расчёт врёт — флаг, а не число без оговорки


def _step_from_unit(per: str) -> tuple[str, float]:
    """Шаг «заметного изменения» для переменной компании по её единице: проценты/п.п. → 1 п.п.,
    доллары → 10, рубли за доллар → 10% от базы, прочее → 10% от базы."""
    u = per.lower()
    if "п.п" in u or "%" in u:
        return ("abs", 1.0)
    if "долл" in u or "$" in u:
        return ("abs", 10.0)
    return DEFAULT_STEP


def profit_base(base_fin: dict) -> float | None:
    """База чистой прибыли для сценариев: устойчивая база `net_profit_base` (методика 2.1 — если
    нормализованная прибыль карточки всё ещё несёт разовые/неповторяющиеся статьи, модельер задаёт
    устойчивую базу и мост к ней в `base_bridge`), иначе нормализованная `net_profit_adjusted`."""
    v = base_fin.get("net_profit_base")
    if isinstance(v, (int, float)):
        return float(v)
    v = base_fin.get("net_profit_adjusted")
    return float(v) if isinstance(v, (int, float)) else None


# ----------------------------- загрузка -----------------------------
def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_model(ticker: str) -> dict | None:
    p = COMPANIES_DIR / ticker.upper() / "macro_model.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ----------------------------- утилиты -----------------------------
def _rng(v) -> tuple[float, float, float] | None:
    """Число или {'low','high'[,'mid']} → (low, mid, high). None — нет значения."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return (f, f, f)
    if isinstance(v, dict):
        lo, hi = v.get("low"), v.get("high")
        if lo is None and hi is None:
            b = v.get("base", v.get("mid", v.get("value")))
            if b is None:
                return None
            return (float(b), float(b), float(b))
        if lo is None:
            lo = hi
        if hi is None:
            hi = lo
        lo, hi = float(lo), float(hi)
        if lo > hi:
            lo, hi = hi, lo
        mid = v.get("mid", v.get("base"))
        mid = float(mid) if mid is not None else (lo + hi) / 2.0
        return (lo, mid, hi)
    return None


def _r(x, nd=1):
    return None if x is None else round(float(x), nd)


def _pct(delta, base):
    if base in (None, 0):
        return None
    return round(delta / abs(base) * 100.0, 1)


def scenario_ids(cfg: dict) -> list[str]:
    return [s["id"] for s in cfg.get("scenarios", [])]


def scenario_name(cfg: dict, sid: str) -> str:
    for s in cfg.get("scenarios", []):
        if s["id"] == sid:
            return s.get("name", sid)
    return sid


def base_vector(cfg: dict, model: dict) -> dict[str, float]:
    """Значения переменных в базовом периоде: общие + достройки компании."""
    vec = {k: float(v) for k, v in (cfg.get("base_period", {}).get("values") or {}).items()
           if isinstance(v, (int, float))}
    for var, spec in (model.get("scenario_inputs") or {}).items():
        b = spec.get("base_period_value")
        if isinstance(b, (int, float)):
            vec[var] = float(b)
    return vec


def scenario_vector(cfg: dict, model: dict, sid: str, year: int | str) -> dict[str, tuple[float, float, float]]:
    """Значения переменных сценария в году: (low, mid, high). Общие + достройки ЦБ-файла + достройки компании."""
    y = str(year)
    out: dict[str, tuple[float, float, float]] = {}
    scen = next((s for s in cfg.get("scenarios", []) if s["id"] == sid), None)
    if scen is None:
        raise KeyError(f"сценарий {sid} не найден в конфиге")
    for var, v in (scen.get("years", {}).get(y) or {}).items():
        r = _rng(v)
        if r:
            out[var] = r
    for var, byyear in (scen.get("completions") or {}).items():
        r = _rng((byyear or {}).get(y))
        if r:
            out[var] = r
    for var, spec in (model.get("scenario_inputs") or {}).items():
        r = _rng(((spec.get("by_scenario") or {}).get(sid) or {}).get(y))
        if r:
            out[var] = r
    return out


# ----------------------------- применение объектов -----------------------------
def _coef_multiplier(coef: dict, vec_mid: dict[str, float], delta_mid: float, sid: str, model: dict) -> tuple[float, list[str]]:
    """Множитель к коэффициенту: асимметрия по знаку Δ, пороги по значениям переменных в сценарии,
    модификаторы вида multiply_coef. Возвращает множитель и пояснения."""
    notes: list[str] = []
    mult = 1.0
    asym = coef.get("asymmetry") or {}
    if delta_mid > 0 and isinstance(asym.get("up_multiplier"), (int, float)):
        mult *= float(asym["up_multiplier"])
        if float(asym["up_multiplier"]) != 1.0:
            notes.append(f"асимметрия вверх ×{asym['up_multiplier']}")
    elif delta_mid < 0 and isinstance(asym.get("down_multiplier"), (int, float)):
        mult *= float(asym["down_multiplier"])
        if float(asym["down_multiplier"]) != 1.0:
            notes.append(f"асимметрия вниз ×{asym['down_multiplier']}")
    for t in coef.get("thresholds") or []:
        var = t.get("variable")
        val = vec_mid.get(var)
        lvl = t.get("level")
        if val is None or not isinstance(lvl, (int, float)):
            continue
        cond = t.get("condition", "above")
        hit = (val > lvl) if cond == "above" else (val < lvl)
        if hit and isinstance(t.get("multiplier"), (int, float)):
            mult *= float(t["multiplier"])
            notes.append(f"порог {var} {'>' if cond == 'above' else '<'} {lvl}: ×{t['multiplier']}")
    for mod in model.get("modifiers") or []:
        if mod.get("mode") == "multiply_coef" and mod.get("applies_to") == f"coefficient:{coef.get('id')}":
            r = _rng((mod.get("by_scenario") or {}).get(sid))
            if r and r[1] != 1.0:
                mult *= r[1]
                notes.append(f"модификатор {mod.get('id')}: ×{r[1]}")
    return mult, notes


def _coef_effects(coef: dict, line: str, delta: tuple[float, float, float], mult: float) -> dict | None:
    eff = (coef.get("effects") or {}).get(line)
    r = _rng(eff)
    if r is None:
        return None
    c_lo, c_base, c_hi = r
    d_lo, d_mid, d_hi = delta
    combos = [c * d * mult for c in (c_lo, c_base, c_hi) for d in (d_lo, d_mid, d_hi)]
    return {"base": c_base * d_mid * mult, "low": min(combos), "high": max(combos)}


def _modifier_effects(model: dict, line: str, sid: str) -> list[dict]:
    out = []
    for mod in model.get("modifiers") or []:
        if mod.get("mode", "add_bn") != "add_bn" or mod.get("applies_to") != f"line:{line}":
            continue
        r = _rng((mod.get("by_scenario") or {}).get(sid))
        if r is None:
            continue
        lo, mid, hi = r
        if lo == 0 and hi == 0:
            continue
        out.append({"id": mod.get("id"), "label": mod.get("label"), "kind": mod.get("kind"),
                    "base": mid, "low": lo, "high": hi, "is_modifier": True,
                    "origin": mod.get("origin"), "credibility": mod.get("credibility")})
    return out


def run_vector(model: dict, cfg: dict, sid: str, vec: dict[str, tuple[float, float, float]], *, label: str) -> dict:
    """Один расчёт: сценарий (или произвольный вектор) → строки отчётности с диапазонами и атрибуцией.

    Диапазон (методика 10.3) — наборы «все входы в неблагоприятную / благоприятную сторону», но ОДНА
    переменная принимает ОДНО значение внутри набора: коэффициенты с общим `macro_var` (например,
    переоценка активов и пассивов банка по ставке) оцениваются при одном и том же значении ставки.
    Иначе встречные каналы одной переменной раздувают интервал (найдено на SBER)."""
    base_fin = model.get("base_financials") or {}
    bvec = base_vector(cfg, model)
    vec_mid = {k: v[1] for k, v in vec.items()}
    lines_out: dict[str, dict] = {}
    missing_vars: set[str] = set()
    for line in LINES:
        base_line = profit_base(base_fin) if line == "net_profit" else base_fin.get(line)
        if not isinstance(base_line, (int, float)):
            continue
        groups: dict[str, list[dict]] = {}
        for coef in model.get("coefficients") or []:
            var = coef.get("macro_var")
            if _rng((coef.get("effects") or {}).get(line)) is None:
                continue
            if var not in vec or var not in bvec:
                if var not in vec:
                    missing_vars.add(var)
                continue
            groups.setdefault(var, []).append(coef)
        contribs: list[dict] = []
        total_base = total_low = total_high = 0.0
        for var, cs in groups.items():
            lo, mid, hi = vec[var]
            b = bvec[var]
            deltas = {"low": lo - b, "mid": mid - b, "high": hi - b}
            per_base: dict[str, tuple[float, list[str]]] = {}
            for c in cs:
                mult, notes = _coef_multiplier(c, vec_mid, deltas["mid"], sid, model)
                per_base[c["id"]] = (_rng(c["effects"][line])[1] * deltas["mid"] * mult, notes)
            best_low = best_high = None
            for dk, d in deltas.items():
                vec_c = dict(vec_mid)
                vec_c[var] = b + d
                mins: dict[str, float] = {}
                maxs: dict[str, float] = {}
                for c in cs:
                    mult, _ = _coef_multiplier(c, vec_c, d, sid, model)
                    c_lo, c_base, c_hi = _rng(c["effects"][line])
                    vals = [c_lo * d * mult, c_base * d * mult, c_hi * d * mult]
                    mins[c["id"]] = min(vals)
                    maxs[c["id"]] = max(vals)
                s_min, s_max = sum(mins.values()), sum(maxs.values())
                if best_low is None or s_min < best_low[0]:
                    best_low = (s_min, mins, dk)
                if best_high is None or s_max > best_high[0]:
                    best_high = (s_max, maxs, dk)
            for c in cs:
                cb, notes = per_base[c["id"]]
                contribs.append({"id": c.get("id"), "label": c.get("label"), "var": var,
                                 "delta_var": _r(deltas["mid"], 3), "var_from": _r(b, 3), "var_to": _r(mid, 3),
                                 "base": cb, "low": best_low[1][c["id"]], "high": best_high[1][c["id"]],
                                 "var_value_in_low_set": _r(b + deltas[best_low[2]], 3),
                                 "var_value_in_high_set": _r(b + deltas[best_high[2]], 3),
                                 "origin": c.get("origin"), "credibility": c.get("credibility"),
                                 "notes": notes, "is_modifier": False})
            total_base += sum(v[0] for v in per_base.values())
            total_low += best_low[0]
            total_high += best_high[0]
        for m in _modifier_effects(model, line, sid):
            contribs.append(m)
            total_base += m["base"]
            total_low += m["low"]
            total_high += m["high"]
        width = total_high - total_low
        for c in contribs:
            c["width_share_pct"] = _r((c["high"] - c["low"]) / width * 100.0, 1) if width > 0 else 0.0
            for k in ("base", "low", "high"):
                c[k] = _r(c[k], 2)
        dominant = max(contribs, key=lambda c: abs(c["base"] or 0), default=None)
        lines_out[line] = {
            "label": LINE_LABELS[line],
            "base_year_value": _r(base_line, 1),
            "delta": {"base": _r(total_base), "low": _r(total_low), "high": _r(total_high)},
            "value": {"base": _r(base_line + total_base), "low": _r(base_line + total_low), "high": _r(base_line + total_high)},
            "pct": {"base": _pct(total_base, base_line), "low": _pct(total_low, base_line), "high": _pct(total_high, base_line)},
            "dominant_factor": (dominant or {}).get("label"),
            "dominant_factor_id": (dominant or {}).get("id"),
            "contributions": sorted(contribs, key=lambda c: -abs(c["base"] or 0)),
            "width_drivers": [c["id"] for c in sorted(contribs, key=lambda c: -abs(c["width_share_pct"] or 0))[:3]],
        }
    flags = []
    rev = lines_out.get("revenue")
    if rev and rev["pct"]["base"] is not None and abs(rev["pct"]["base"]) > LINEARITY_LIMIT_PCT:
        flags.append(f"изменение выручки {rev['pct']['base']:+.0f}% — за пределами зоны, где линейный расчёт надёжен")
    npf = lines_out.get("net_profit")
    if npf and npf["value"]["low"] is not None and npf["value"]["low"] < 0:
        flags.append("при неблагоприятных значениях входов прибыль уходит в убыток")
    if npf and npf["pct"]["base"] is not None and abs(npf["pct"]["base"]) > 2 * LINEARITY_LIMIT_PCT:
        flags.append(f"изменение прибыли {npf['pct']['base']:+.0f}% — линейность под вопросом, читать как порядок величины")
    return {"label": label, "scenario_id": sid, "conditions": {k: {"low": _r(v[0], 2), "mid": _r(v[1], 2), "high": _r(v[2], 2)} for k, v in vec.items()},
            "lines": lines_out, "flags": flags, "missing_vars": sorted(v for v in missing_vars if v)}


# ----------------------------- сценарии, опасный, привязки, стоимость -----------------------------
def run_scenarios(model: dict, cfg: dict) -> dict:
    years = cfg.get("display_years") or [2026, 2027, 2028]
    out: dict[str, dict] = {}
    for s in cfg.get("scenarios", []):
        sid = s["id"]
        out[sid] = {"name": s.get("name", sid), "description": s.get("description"), "years": {}}
        for y in years:
            vec = scenario_vector(cfg, model, sid, y)
            out[sid]["years"][str(y)] = run_vector(model, cfg, sid, vec, label=f"{s.get('name', sid)} {y}")
    return out


def run_most_dangerous(model: dict, cfg: dict) -> dict | None:
    md = model.get("most_dangerous") or {}
    adverse = md.get("adverse_values") or {}
    if not adverse:
        return None
    vec = {}
    for var, v in adverse.items():
        r = _rng(v)
        if r:
            vec[var] = r
    sid = md.get("modifiers_key", "most_dangerous")
    res = run_vector(model, cfg, sid, vec, label="наиболее опасный (не прогноз)")
    res["description"] = md.get("description")
    res["break_points"] = md.get("break_points") or []
    res["note"] = "Сценарий-предел: неблагоприятные значения факторов, к которым компания чувствительнее всего, плюс модификаторы в эскалационной траектории. Не прогноз и не взвешен вероятностью (методика 10.4)."
    return res


def anchors(model: dict, cfg: dict) -> list[dict]:
    """Числовые привязки: эффект «заметного» изменения переменной на строки (для блока 2 вкладки)."""
    bvec = base_vector(cfg, model)
    out = []
    for coef in model.get("coefficients") or []:
        var = coef.get("macro_var")
        b = bvec.get(var)
        kind, size = STEPS.get(var) or _step_from_unit(coef.get("per") or "")
        step = size if kind == "abs" else (abs(b) * size if b else None)
        if step is None:
            continue
        vec_mid = dict(bvec)
        vec_mid[var] = (b or 0) + step
        mult, notes = _coef_multiplier(coef, vec_mid, step, "base", model)
        effects = {}
        for line in LINES:
            e = _coef_effects(coef, line, (step, step, step), mult)
            if e:
                effects[line] = {k: _r(v, 1) for k, v in e.items()}
        if not effects:
            continue
        unit = coef.get("per") or ""
        if kind == "rel":
            step_text = f"+{int(size * 100)}% ({step:+.1f} {unit.split('/')[0].replace('+1 ', '') if unit else ''})".replace("( ", "(").strip()
        else:
            step_text = f"{step:+g} {unit.replace('+1 ', '') if unit else ''}".strip()
        out.append({"anchor_id": coef.get("id"), "label": coef.get("label"), "var": var,
                    "step": _r(step, 3), "step_kind": kind, "step_text": step_text,
                    "effects_bn": effects, "origin": coef.get("origin"), "credibility": coef.get("credibility"),
                    "notes": notes})
    return out


def rate_valuation(model: dict, cfg: dict) -> dict | None:
    """Эффект +1 п.п. ключевой ставки на стоимость: канал оценки (−перенос/(r−g)) + канал прибыли."""
    vl = model.get("valuation_link") or {}
    r = vl.get("required_return_pct")
    g = vl.get("terminal_growth_pct")
    p = _rng(vl.get("rate_to_required_return_passthrough"))
    if not isinstance(r, (int, float)) or not isinstance(g, (int, float)) or p is None or r <= g:
        return None
    spread = float(r) - float(g)
    val_lo = -p[2] / spread * 100.0  # больший перенос → сильнее падение
    val_hi = -p[0] / spread * 100.0
    base_np = profit_base(model.get("base_financials") or {})
    prof = {"low": None, "base": None, "high": None}
    coef_sum = {"low": 0.0, "base": 0.0, "high": 0.0}
    for coef in model.get("coefficients") or []:
        if coef.get("macro_var") != "key_rate_avg":
            continue
        e = _coef_effects(coef, "net_profit", (1.0, 1.0, 1.0), 1.0)
        if e:
            for k in coef_sum:
                coef_sum[k] += e[k]
    if isinstance(base_np, (int, float)) and base_np > 0:
        prof = {k: _r(v / base_np * 100.0, 1) for k, v in coef_sum.items()}
    total = None
    if prof["base"] is not None:
        total = {"low": _r(val_lo + prof["low"], 1), "high": _r(val_hi + prof["high"], 1)}
    return {"per": "+1 п.п. ключевой ставки",
            "valuation_channel_pct": {"low": _r(val_lo, 1), "high": _r(val_hi, 1),
                                      "formula": "ΔV/V ≈ −перенос ставки в требуемую доходность / (r − g)",
                                      "r_pct": r, "g_pct": g, "passthrough": {"low": p[0], "high": p[2]}},
            "profit_channel_pct": prof, "profit_channel_bn": {k: _r(v, 1) for k, v in coef_sum.items()},
            "total_pct": total,
            "note": "оценка; зависит от допущений о темпе роста и структуре денежных потоков (спецификация 5.3)",
            "profit_timing": vl.get("profit_timing"), "dividend_role": vl.get("dividend_role"),
            "leverage_note": vl.get("leverage_note"), "origin": vl.get("origin")}


def integrity_checks(model: dict) -> list[str]:
    bf = model.get("base_financials") or {}
    issues = []
    rev, ebitda, np_ = bf.get("revenue"), bf.get("ebitda"), bf.get("net_profit_adjusted")
    if isinstance(rev, (int, float)) and isinstance(ebitda, (int, float)) and ebitda > rev:
        issues.append("EBITDA больше выручки")
    if isinstance(ebitda, (int, float)) and isinstance(np_, (int, float)) and np_ > ebitda:
        issues.append("чистая прибыль больше EBITDA")
    if not model.get("coefficients"):
        issues.append("нет коэффициентов")
    for coef in model.get("coefficients") or []:
        for line, eff in (coef.get("effects") or {}).items():
            r = _rng(eff)
            if r is None:
                continue
            lo, base, hi = r
            if not (lo <= base <= hi):
                issues.append(f"{coef.get('id')}/{line}: база {base} вне диапазона [{lo}, {hi}]")
        if coef.get("credibility") not in (1, 2, 3):
            issues.append(f"{coef.get('id')}: не задан уровень достоверности 1/2/3")
        if not coef.get("derivation"):
            issues.append(f"{coef.get('id')}: нет выкладки (derivation)")
    return issues


def compute(ticker: str, cfg: dict | None = None) -> dict | None:
    model = load_model(ticker)
    if model is None:
        return None
    cfg = cfg or load_config()
    res = {
        "ticker": ticker.upper(),
        "computed_at": date.today().isoformat(),
        "unit": "млрд руб",
        "base_year": (model.get("base_financials") or {}).get("year"),
        "base_financials": model.get("base_financials"),
        "cbr_scenarios": {"as_of": cfg.get("as_of"), "source": cfg.get("source"), "display_years": cfg.get("display_years"),
                          "tab_years": cfg.get("tab_years")},
        "current_macro": cfg.get("current"),
        "scenarios": run_scenarios(model, cfg),
        "most_dangerous": run_most_dangerous(model, cfg),
        "anchors": anchors(model, cfg),
        "rate_valuation": rate_valuation(model, cfg),
        "integrity_issues": integrity_checks(model),
        "method_note": "Линейный расчёт от фактического результата базового года: Δстроки = Σ коэффициент × Δпеременной (× асимметрия × пороги) + модификаторы. Без лагов, без управленческой реакции, при неизменной структуре бизнеса (спецификация вкладки 4.3–4.4). Диапазон — наборы «все входы в неблагоприятную/благоприятную сторону» (методика 10.3), причём одна переменная принимает одно значение внутри набора для всех коэффициентов на неё.",
    }
    return res


def write(ticker: str, cfg: dict | None = None) -> Path | None:
    res = compute(ticker, cfg)
    if res is None:
        return None
    p = COMPANIES_DIR / ticker.upper() / "macro_scenarios.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ----------------------------- отладочный текст -----------------------------
def render_md(res: dict) -> str:
    L = [f"# {res['ticker']} — сценарные результаты (база {res.get('base_year')}, {res['unit']})"]
    bf = res.get("base_financials") or {}
    L.append(f"База: выручка {bf.get('revenue')}, EBITDA {bf.get('ebitda')}, ЧП для сценариев {profit_base(bf)} (нормализованная {bf.get('net_profit_adjusted')}, отчётная {bf.get('net_profit_reported')})")
    for sid, s in (res.get("scenarios") or {}).items():
        L.append(f"\n## {s['name']}")
        for y, r in s["years"].items():
            parts = []
            for line, lo in r["lines"].items():
                parts.append(f"{lo['label']}: {lo['value']['low']}…{lo['value']['base']}…{lo['value']['high']} ({lo['pct']['low']}…{lo['pct']['high']}%; доминант: {lo['dominant_factor']})")
            L.append(f"- {y}: " + " | ".join(parts))
            if r["flags"]:
                L.append("  флаги: " + "; ".join(r["flags"]))
            if r["missing_vars"]:
                L.append("  нет переменных в сценарии: " + ", ".join(r["missing_vars"]))
    md = res.get("most_dangerous")
    if md:
        L.append("\n## Наиболее опасный (не прогноз)")
        for line, lo in md["lines"].items():
            L.append(f"- {lo['label']}: {lo['value']['low']}…{lo['value']['base']}…{lo['value']['high']} ({lo['pct']['base']}%)")
    L.append("\n## Числовые привязки")
    for a in res.get("anchors") or []:
        L.append(f"- {a['label']} {a['step_text']}: " + ", ".join(f"{LINE_LABELS[k]} {v['base']} [{v['low']}…{v['high']}]" for k, v in a["effects_bn"].items()) + f" — {a['origin']}, ур. {a['credibility']}")
    rv = res.get("rate_valuation")
    if rv:
        L.append(f"\n## Ставка → стоимость: оценка {rv['valuation_channel_pct']['low']}…{rv['valuation_channel_pct']['high']}% на 1 п.п.; прибыль {rv['profit_channel_pct']}; итого {rv['total_pct']}")
    if res.get("integrity_issues"):
        L.append("\n## Проблемы целостности: " + "; ".join(res["integrity_issues"]))
    return "\n".join(L)


if __name__ == "__main__":  # pragma: no cover
    import sys
    for t in sys.argv[1:]:
        p = write(t)
        print(p)
        if p:
            print(render_md(json.loads(p.read_text(encoding="utf-8"))))
