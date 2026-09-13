"""Справочник населённых пунктов Украины (OSM, ODbL) — привязка заявления о
взятии к координате по имени + области (+ район, + близость к фронту).

Владелец (2026-09-14): «сделай» — вместо защиты по 64 городам полный справочник,
который убирает класс ошибок геокодинга целиком. Боевые случаи, ради которых он
нужен: «Новопавловка Запорожской области» получила координаты центра Орехова
(город закрасился взятым); «Красный Кут Донецкой области» уехал в Саратовскую
(тёзка); сёла из сводок МО РФ названы СТАРЫМИ именами («Красноармейск»,
«Димитров»), которых нет в заголовках Википедии.

Файл — config/geo_ua_settlements.json.gz, собирается
scripts/geo_ua_gazetteer_build.py (см. там источники и поля). Здесь — только
чтение и разрешение имени. Честная деградация: файла нет → resolve() отдаёт
status=no_gazetteer, вызывающие работают по прежним правилам.

Статусы resolve():
  exact       — одно совпадение (с учётом области/района);
  near_front  — тёзок несколько, ровно одна рядом с фронтом (near/max_km);
  fuzzy       — точного нет, одно совпадение с опечаткой/иным написанием;
  ambiguous   — несколько тёзок, развести нечем (координату НЕ выдаём);
  not_found   — имени нет в справочнике;
  no_gazetteer — справочник не загружен.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "config", "geo_ua_settlements.json.gz")
_KM_PER_DEG = 111.0
_lock = threading.Lock()
_loaded: dict | None = None  # {"items": [...], "index": {norm: [i, ...]}, "by_oblast": {obl: [i, ...]}}

# Служебные слова перед названием в сводках («село Новопавловка», «н.п. Х»).
_PREFIX_RE = re.compile(
    r"^(?:н\.?\s?п\.?|нп|с\.|село|сел\.|пос\.|посёлок|поселок|пгт\.?|смт\.?|г\.|город|м\.|місто|"
    r"хутор|х\.|станция|ст\.|деревня|д\.)\s+", re.IGNORECASE)
_APOS_RE = re.compile(r"[’'`ʼ\"«»]")
_SEP_RE = re.compile(r"[\s\-–—]+")

# Украинское написание → русское, грубо: достаточно, чтобы сойтись с расстоянием
# редактирования ≤ 2 (точных правил нет: «Новопавлівка» → «Новопавловка», но
# «Мар’їнка» → «Марьинка»). Порядок важен: сначала суффиксы, потом буквы.
_UK_SUFFIXES = (
    ("івка", "овка"), ("ївка", "евка"), ("ське", "ское"), ("ська", "ская"), ("ський", "ский"),
    ("цьке", "цкое"), ("цька", "цкая"), ("цький", "цкий"), ("ний", "ный"), ("нє", "нее"),
    ("ий", "ый"), ("є", "е"),
)
_UK_CHARS = str.maketrans({"і": "и", "ї": "и", "є": "е", "ґ": "г"})
# Корни, где украинское и русское написание расходятся не по буквам, а по слову:
# «Миколаївка» — «Николаевка» (самое частое имя села на Украине).
_UK_ROOTS = (("микола", "никола"), ("михайл", "михайл"), ("олексі", "алексе"), ("олекс", "алекс"),
             ("дмитр", "дмитр"), ("василь", "василь"), ("андрі", "андре"))


def normalize(name: str | None) -> str:
    """Ключ сравнения: без служебных слов, регистра, ё, апострофов, пробелов и дефисов."""
    if not name:
        return ""
    s = name.strip()
    s = s.split("(")[0] if "(" in s and not s.startswith("(") else s
    s = _PREFIX_RE.sub("", s)
    s = s.lower().replace("ё", "е")
    s = _APOS_RE.sub("", s)
    s = _SEP_RE.sub("", s)
    # Мягкий/твёрдый знак не различает сёла, а написания расходятся: в OSM
    # русское имя Василівки — «Василевка», в сводках МО РФ — «Васильевка».
    return s.replace("ь", "").replace("ъ", "")


def uk_to_ru(name: str | None) -> str:
    """Приближённая транслитерация украинского написания в русское (см. выше)."""
    return uk_to_ru_variants(name)[0] if normalize(name) else ""


def uk_to_ru_variants(name: str | None) -> list[str]:
    """Все правдоподобные русские написания украинского имени. Одного правила
    нет: «Іванівка» → «Ивановка», но «Василівка» → «Васильевка», «Андріївка» →
    «Андреевка» — по украинскому написанию не понять, мягкая ли основа.
    Индексируем оба варианта; ложное совпадение отсекут область и подсказка."""
    s = normalize(name)
    if not s:
        return []
    out = []
    stem, tail = s, ""
    for uk, ru in _UK_SUFFIXES:
        if s.endswith(uk):
            stem, tail = s[: -len(uk)], ru
            break
    variants = [stem + tail]
    if tail == "овка" and stem and stem[-1] in "лнтдсрц":
        variants.append(stem + "ьевка")   # Василівка → Васильевка, Ільлівка → Ильевка
    for v in variants:
        for uk, ru in _UK_ROOTS:
            if uk in v:
                v = v.replace(uk, ru)
        v = v.translate(_UK_CHARS)
        if v not in out:
            out.append(v)
    return out


def oblast_key(text: str | None) -> str | None:
    """«Донецкая область (Покровский район)» / «ДНР» / «Запорожская» → «донецкая» /
    «донецкая» / «запорожская». None — область не названа."""
    if not text:
        return None
    t = text.strip().lower().replace("ё", "е")
    if not t:
        return None
    if t.startswith("днр") or "донецкая народная" in t:
        return "донецкая"
    if t.startswith("лнр") or "луганская народная" in t:
        return "луганская"
    if "крым" in t:
        return "крым"
    if t.startswith("киев") and "област" not in t:
        return "киев"
    head = t.split("(")[0].split(",")[0].strip()
    words = [w for w in head.split() if w not in ("область", "обл.", "обл", "республика")]
    return words[0].strip(".,") if words else None


def raion_key(text: str | None) -> str | None:
    """Район из скобок «(Волчанский район)» либо из явной строки → «волчанский»."""
    if not text:
        return None
    t = text.strip().lower().replace("ё", "е")
    m = re.search(r"\(([^)]*район[^)]*)\)", t)
    src = m.group(1) if m else (t if "район" in t else "")
    words = [w for w in src.replace(",", " ").split() if w not in ("район", "р-н", "р-он")]
    return words[0].strip(".") if words else None


def _levenshtein(a: str, b: str, cap: int) -> int:
    """Расстояние редактирования с потолком cap (дальше не считаем)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def load(path: str | None = None) -> dict | None:
    """Ленивая загрузка + индекс по всем написаниям (русское, украинское, старые и
    альтернативные, транслитерация украинского). Один раз на процесс."""
    global _loaded
    if _loaded is not None and path is None:
        return _loaded
    p = path or _PATH
    if not os.path.exists(p):
        return None
    with _lock:
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001 — справочник вторичен
            logger.warning("Справочник НП не прочитан", exc_info=True)
            return None
        items = data.get("items") or []
        index: dict[str, list[int]] = {}
        by_oblast: dict[str, list[int]] = {}

        def put(key: str, i: int):
            if key:
                lst = index.setdefault(key, [])
                if i not in lst:
                    lst.append(i)

        for i, it in enumerate(items):
            it["_o"] = (it.get("o") or "").lower().replace("ё", "е") or None
            it["_r"] = (it.get("r") or "").lower().replace("ё", "е") or None
            put(normalize(it.get("n")), i)
            put(normalize(it.get("u")), i)
            for v in uk_to_ru_variants(it.get("u")):
                put(v, i)
            for a in it.get("a") or []:
                put(normalize(a), i)
                for v in uk_to_ru_variants(a):
                    put(v, i)
            if it["_o"]:
                by_oblast.setdefault(it["_o"], []).append(i)
        built = {"items": items, "index": index, "by_oblast": by_oblast,
                 "generated_at": data.get("generated_at"), "count": len(items)}
        if path is None:
            _loaded = built
        return built


def _hit(it: dict, status: str, n: int) -> dict:
    return {"lat": it["lat"], "lon": it["lon"], "name": it.get("n") or it.get("u"),
            "oblast": it.get("o"), "raion": it.get("r"), "place": it.get("t"), "osm_id": it.get("id"),
            "status": status, "candidates": n}


_HINT_KM = 10.0        # тёзки: прежняя координата в 10 км от одной из них — это она
_SAME_PLACE_KM = 3.0   # одноимённые записи ближе 3 км — одно и то же село (узел + контур)
_FUZZY_HINT_KM = 20.0  # приблизительное совпадение принимаем только рядом с прежней координатой


def resolve(name: str | None, oblast: str | None = None, raion: str | None = None,
            near=None, max_km: float = 25.0, hint: tuple[float, float] | None = None,
            gz: dict | None = None) -> dict:
    """Имя (+ область, + район, + геометрия фронта, + прежняя координата) → координата.
    near — shapely-геометрия (масса контроля/плацдарм): среди тёзок берём ту,
    что не дальше max_km от неё, если такая ровно одна. hint — координата, с
    которой пункт пришёл (геокодинг статьи): среди оставшихся тёзок берём ту,
    что в _HINT_KM от неё; приблизительное совпадение имени принимаем ТОЛЬКО
    рядом с ней — иначе опечатка уводила село на 90 км к похожему имени.

    Точное имя есть, но не в названной области: область в сводке бывает
    ошибочной, поэтому такую тёзку принимаем лишь если её выделяет фронт или
    прежняя координата; иначе status=oblast_mismatch без координаты — точка за
    сотни километров хуже, чем пункт без точки."""
    from shapely.geometry import Point

    gz = gz or load()
    if gz is None:
        return {"status": "no_gazetteer", "candidates": 0}
    key = normalize(name)
    if not key:
        return {"status": "not_found", "candidates": 0}
    obl = oblast_key(oblast)
    rai = raion_key(raion) or raion_key(oblast)
    items = gz["items"]
    hint_pt = Point(hint[1], hint[0]) if hint and hint[0] is not None and hint[1] is not None else None

    def _within(i: int, pt, km: float) -> bool:
        return pt.distance(Point(items[i]["lon"], items[i]["lat"])) * _KM_PER_DEG <= km

    def _fuzzy(pool) -> list[int]:
        """Опечатка / иное написание (в т.ч. старое имя по-украински): ближайшие
        по расстоянию редактирования ключи в pool."""
        cap = 1 if len(key) < 9 else 2
        if len(key) < 5:
            return []
        best: dict[int, int] = {}
        seen_keys: dict[str, int] = {}
        for i in pool:
            it = items[i]
            alt_keys = [k for a in (it.get("a") or []) for k in (normalize(a), *uk_to_ru_variants(a))]
            for cand_key in (normalize(it.get("n")), *uk_to_ru_variants(it.get("u")), *alt_keys):
                if not cand_key or cand_key[0] != key[0]:
                    continue
                if cand_key in seen_keys:
                    d = seen_keys[cand_key]
                else:
                    d = _levenshtein(key, cand_key, cap)
                    seen_keys[cand_key] = d
                if d <= cap and (i not in best or d < best[i]):
                    best[i] = d
        if not best:
            return []
        dmin = min(best.values())
        return [i for i, d in best.items() if d == dmin]

    def _disambiguate(cands: list[int]) -> tuple[list[int], str | None]:
        """Тёзки: район → фронт → прежняя координата. Возвращает (оставшиеся,
        чем развели). Фронт раньше подсказки: подсказка — геокодинг статьи,
        который сам бывает тёзкой за сотни километров."""
        if len(cands) > 1 and rai:
            in_rai = [i for i in cands if items[i]["_r"] == rai]
            if in_rai:
                cands = in_rai
        if len(cands) > 1 and near is not None and not near.is_empty:
            close = [i for i in cands if _within(i, near, max_km)]
            if len(close) == 1:
                return close, "near_front"
            if close:
                cands = close
        if len(cands) > 1 and hint_pt is not None:
            by_hint = [i for i in cands if _within(i, hint_pt, _HINT_KM)]
            if len(by_hint) == 1:
                return by_hint, None
            if by_hint:
                cands = by_hint
        # Одноимённые записи в паре километров друг от друга — одно село (узел и
        # контур, две точки одного пункта), а не тёзки: берём узел или первую.
        if len(cands) > 1:
            pts = [Point(items[i]["lon"], items[i]["lat"]) for i in cands]
            if all(a.distance(b) * _KM_PER_DEG <= _SAME_PLACE_KM for a in pts for b in pts):
                nodes_ = [i for i in cands if str(items[i].get("id", "")).startswith("n")]
                return [nodes_[0] if nodes_ else cands[0]], None
        return cands, None

    def _fuzzy_ok(i: int) -> bool:
        """Приблизительное совпадение принимаем, только если оно рядом с фронтом
        или с прежней координатой (когда есть, с чем сравнить): иначе опечатка
        уводила село на 90 км к похожему имени."""
        if near is not None and not near.is_empty and _within(i, near, max_km):
            return True
        if hint_pt is not None:
            return _within(i, hint_pt, _FUZZY_HINT_KM)
        return near is None or near.is_empty

    ids = list(gz["index"].get(key, []))
    status = "exact"
    if not ids:
        # без области перебор по всей стране даёт ложные «похожие» имена — ищем
        # только внутри названной области (или везде, если её нет, но тогда
        # спасает лишь фронт/подсказка)
        ids = _fuzzy(gz["by_oblast"].get(obl, []) if obl else range(len(items)))
        status = "fuzzy"
        if not ids:
            return {"status": "not_found", "candidates": 0}

    if obl:
        in_obl = [i for i in ids if items[i]["_o"] == obl]
        if in_obl:
            ids = in_obl
        elif status == "fuzzy":
            return {"status": "not_found", "candidates": 0}
        else:
            # Точное имя есть, но не в названной области. Сначала — иное
            # написание ВНУТРИ названной области (село переименовано, старое имя
            # в справочнике только по-украински: «Коммунаровка» → Христофоровка);
            # лишь потом — тёзка из другой области, и только если на неё
            # указывает фронт или прежняя координата.
            fz, _ = _disambiguate(_fuzzy(gz["by_oblast"].get(obl, [])))
            if len(fz) == 1 and _fuzzy_ok(fz[0]):
                return _hit(items[fz[0]], "fuzzy", 1)
            picked, _ = _disambiguate(ids)
            if len(picked) == 1:
                return _hit(items[picked[0]], "near_front", len(ids))
            return {"status": "oblast_mismatch", "candidates": len(ids),
                    "options": [{"name": items[i].get("n") or items[i].get("u"), "oblast": items[i].get("o")}
                                for i in ids[:6]]}

    n_before = len(ids)
    ids, how = _disambiguate(ids)
    if len(ids) == 1:
        if status == "fuzzy" and not _fuzzy_ok(ids[0]):
            return {"status": "not_found", "candidates": 0}
        return _hit(items[ids[0]], how or status, n_before)
    return {"status": "ambiguous", "candidates": len(ids),
            "options": [{"name": items[i].get("n") or items[i].get("u"), "oblast": items[i].get("o"),
                         "raion": items[i].get("r"), "lat": items[i]["lat"], "lon": items[i]["lon"]}
                        for i in ids[:6]]}
