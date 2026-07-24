import re
import json

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
MONTH_ALT = "|".join(MONTHS)

RUSSIA_BG = "#DA291C50"

KEYWORD_RE = re.compile(r"(Captured|Recaptured|Retaken)\s+by\b", re.IGNORECASE)
DATE_ANY_RE = re.compile(
    # "on"/"around"/"as of"/"by" DATE, ИЛИ дата вообще без предлога сразу после
    # актора (напр. "Recaptured by {{RUS}} 16 January 2023") — день-диапазон
    # вида "24–25 December 2023" берём ПЕРВЫЙ день диапазона
    r"(?:(?:on|around|as of|by)\s+)?(?P<d1>\d{1,2})(?:\s*[-–—]\s*\d{1,2})?\s+(?P<d1mon>" + MONTH_ALT + r")\s+(?P<d1yr>\d{4})"
    r"|in\s+(?:early|mid|late)?-?\s*(?P<d2>(?:" + MONTH_ALT + r")\s+\d{4})"
    r"|in\s+(?P<d3>\d{4})(?!\d)"
)

# {{RUS}}/{{UKR}} — частые шаблоны-сокращения БЕЗ буквального слова Russia/Ukraine
RUSSIA_SIDE_RE = re.compile(
    r"Russia|Donetsk People's Republic|Luhansk People's Republic|\bDPR\b|\bLPR\b|\{\{RUS\}\}", re.IGNORECASE)
UKRAINE_SIDE_RE = re.compile(r"Ukraine|\{\{UKR\}\}", re.IGNORECASE)


def parse_date(d1, d1mon, d1yr, d2, d3):
    if d1:
        return f"{d1yr}-{MONTHS[d1mon]:02d}-{int(d1):02d}", "day"
    if d2:
        m = re.match(r"(\w+)\s+(\d{4})", d2)
        mon, y = m.groups()
        return f"{y}-{MONTHS[mon]:02d}-15", "month"
    if d3:
        return f"{d3}-07-01", "year"
    return None, None


def find_events(cell_text):
    """Находит все 'Captured/Recaptured/Retaken by <actor> on/in <date>' — окно
    от каждого ключевого слова ДО следующего такого же ключевого слова (или до
    конца текста), чтобы 'actor'/дата не перетекали через границу события (это
    и было причиной неверной классификации в первой версии парсера)."""
    kw_positions = [(m.start(), m.end()) for m in KEYWORD_RE.finditer(cell_text)]
    events = []
    for i, (kstart, kend) in enumerate(kw_positions):
        window_end = kw_positions[i + 1][0] if i + 1 < len(kw_positions) else len(cell_text)
        window = cell_text[kend:window_end]
        dm = DATE_ANY_RE.search(window)
        if not dm:
            continue
        actor_text = window[: dm.start()]
        date_iso, precision = parse_date(dm.group("d1"), dm.group("d1mon"), dm.group("d1yr"), dm.group("d2"), dm.group("d3"))
        if not date_iso:
            continue
        has_ru = bool(RUSSIA_SIDE_RE.search(actor_text))
        has_ua = bool(UKRAINE_SIDE_RE.search(actor_text))
        if has_ru and not has_ua:
            side = "ru"
        elif has_ua and not has_ru:
            side = "ua"
        else:
            side = "unknown"
        events.append((date_iso, precision, side))
    return events


ILL_RE = re.compile(r"\{\{ill\|([^}]+)\}\}", re.IGNORECASE)


def name_from_first_cell(cell_text):
    """Первая ячейка строки — либо обычная вики-ссылка [[Target|Display]],
    либо {{ill|Target|lt=Display|uk|...}} (интервики-шаблон для статей без
    английской версии — частый случай для мелких сёл). Если ни то, ни
    другое — считаем ячейку нераспознанной (None), НЕ подставляем название
    из более поздней колонки (это и была причина, что десятки разных сёл
    вокруг Покровска все мисклассифицировались как 'Pokrovsk' — та колонка
    громады шла ПОСЛЕ, и regex 'первая ссылка в строке' её подхватывал)."""
    cell_text = cell_text.strip()
    wl = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cell_text)
    if wl:
        return (wl.group(2) or wl.group(1)).strip()
    ill = re.match(r"\{\{ill\|([^}]+)\}\}", cell_text, re.IGNORECASE)
    if ill:
        params = ill.group(1).split("|")
        lt = next((p.split("=", 1)[1] for p in params if p.strip().lower().startswith("lt=")), None)
        if lt:
            return lt.strip()
        return params[0].strip()  # первый позиционный параметр — целевое название
    return None


def extract_rows(section_text, oblast):
    rows = []
    parts = section_text.split("|-")
    for part in parts:
        part = part.strip()
        if not part or part.startswith("{|") or part.startswith("|}"):
            continue
        held_m = re.search(r"style=background:(#[A-Za-z0-9]+)\s*\|\s*\[\[([^\]|]+)", part)
        if not held_m or held_m.group(1) != RUSSIA_BG:
            continue

        cells = re.split(r"\n\s*\|(?!\})", "\n" + part)  # разбить на ячейки по началу строки "| " (не "|}")
        cells = [c for c in cells if c.strip()]
        if not cells:
            continue
        name = name_from_first_cell(cells[0])
        if not name:
            continue  # нераспознанная первая ячейка (редкий формат) — лучше пропустить, чем взять не то

        asof_m = re.search(r"\{\{#invoke:Date table sorting\|main\|(\d{4})\|(\d{1,2})\|(\d{1,2})", part)
        as_of = f"{asof_m.group(1)}-{int(asof_m.group(2)):02d}-{int(asof_m.group(3)):02d}" if asof_m else None

        events = find_events(part)
        ru_events = [e for e in events if e[2] == "ru"]
        capture_date, precision = (None, None)
        if ru_events:
            ru_events.sort(key=lambda e: e[0])
            capture_date, precision, _ = ru_events[-1]

        rows.append({
            "name": name,
            "oblast": oblast,
            "held_by": "Russia",
            "as_of": as_of,
            "capture_date": capture_date,
            "date_precision": precision,
            "n_events_found": len(events),
        })
    return rows


if __name__ == "__main__":
    main_oblasts = ["Kharkiv", "Kherson", "Luhansk", "Zaporizhzhia", "Dnipropetrovsk", "Sumy", "Crimea and Sevastopol"]
    main_text = open("main_article.wikitext", encoding="utf-8").read()
    sections = re.split(r"\n== (.+?) ==\n", main_text)
    main_rows = []
    for i in range(1, len(sections), 2):
        title = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        oblast_name = title.replace(" Oblast", "").strip()
        if oblast_name not in main_oblasts:
            continue
        main_rows.extend(extract_rows(body, oblast_name))

    # Донецкую — ЦЕЛИКОМ из детальной подстатьи, БЕЗ разбивки по заголовкам
    # районов (та разбивка на "== Raion ==" ломала часть строк — проверено:
    # без неё extract_rows находит на 1 строку Avdiivka больше и т.д.)
    donetsk_text = open("donetsk_article.wikitext", encoding="utf-8").read()
    donetsk_rows = extract_rows(donetsk_text, "Donetsk")

    all_rows = main_rows + donetsk_rows

    best = {}
    for r in all_rows:
        key = (r["name"], r["oblast"])
        if key not in best or (r["capture_date"] and not best[key]["capture_date"]):
            best[key] = r
    all_rows = list(best.values())

    with_date = [r for r in all_rows if r["capture_date"]]
    without_date = [r for r in all_rows if not r["capture_date"]]

    print(f"Всего Russia-held строк: {len(all_rows)}")
    print(f"С распознанной датой взятия: {len(with_date)}")
    print(f"БЕЗ даты: {len(without_date)}")
    print()
    for landmark in ["Avdiivka", "Mariupol", "Pokrovsk", "Bakhmut", "Vuhledar", "Marinka", "Soledar"]:
        hit = [r for r in all_rows if r["name"] == landmark]
        print(f"  {landmark}: {hit}")

    json.dump(all_rows, open("parsed_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
