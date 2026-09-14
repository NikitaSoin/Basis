"""Операционный протокол владельца — общее ядро системных заданий всех агентов.

🔴 ЗАЧЕМ (владелец, 2026-09-14). Методички — знание; протокол
(`docs/Операционный_протокол_агента_v1.md`) превращает знание в поведение: оптика лица,
принимающего решения (восемь вопросов), маршрутизация задач по типам, рабочие процессы
«событие / вопрос / сценарий», девять правил рассуждения, самопроверка. Владелец: «это
может быть промптом для системы». Здесь он им становится: выбранные части кладутся ОДНИМ
неизменным блоком в начало системного задания каждого агента (совет, сведение, три
аналитика сводок, экзамен, ИИ-помощник). Блок статичен → DeepSeek кэширует префикс,
повторные вызовы почти бесплатны.

Части 1 (карта базы знаний — её даёт карточка полки), 2 и 11 (память и архитектура —
описание системы, а не поведение агента), 8 (профиль компании — отдельный слой) в ядро
не входят по умолчанию; их можно запросить параметром parts.

Файл читается с диска и кэшируется по времени изменения: правка протокола владельцем
попадает в задания без деплоя.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PATH = os.path.join(_REPO, "docs", "Операционный_протокол_агента_v1.md")

# Части по умолчанию: поведение агента при любой задаче.
DEFAULT_PARTS: tuple[str, ...] = ("Часть 0", "Часть 3", "Часть 4", "Часть 6", "Часть 7", "Часть 9", "10.1", "Приложение")
# Для аналитиков регулярных сводок — плюс порядок регулярного снимка.
STATE_PARTS: tuple[str, ...] = DEFAULT_PARTS + ("Часть 5",)
# Для ИИ-помощника (вопросы пользователя) — коротко: оптика, вопрос, правила.
ASSISTANT_PARTS: tuple[str, ...] = ("Часть 0", "Часть 6", "Часть 9")

_cache: dict[str, tuple[float, str]] = {}


def _read() -> str:
    try:
        with open(PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _split(text: str) -> list[tuple[str, str, str]]:
    """[(уровень 'part'|'sub', ключ, текст)] по заголовкам «## Часть N…», «## Приложение…», «### N.M…»."""
    heads = [(m.start(), m.group(0)) for m in re.finditer(r"^#{2,3} .+$", text, re.M)]
    out: list[tuple[str, str, str]] = []
    for i, (pos, head) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        title = head.lstrip("# ").strip()
        level = "part" if head.startswith("## ") else "sub"
        m = re.match(r"^(Часть\s+\d+|Приложение|\d+\.\d+)", title)
        key = m.group(1) if m else title
        out.append((level, key, text[pos:end]))
    return out


def core_text(parts: tuple[str, ...] | list[str] | None = None) -> str:
    """Ядро протокола для системного задания. Пусто, если файла нет (мягко)."""
    wanted = tuple(parts or DEFAULT_PARTS)
    try:
        mtime = os.path.getmtime(PATH)
    except OSError:
        return ""
    ck = "|".join(wanted)
    hit = _cache.get(ck)
    if hit and hit[0] == mtime:
        return hit[1]
    text = _read()
    if not text:
        return ""
    chunks: list[str] = []
    current_part: str | None = None
    for level, key, body in _split(text):
        if level == "part":
            current_part = key
            if key in wanted:
                chunks.append(body)          # часть целиком (все её подразделы идут следом как отдельные записи —
                                             # они включены в тело части, т.к. _split режет по ### тоже; см. ниже)
        else:
            # подраздел: берём, если его часть выбрана целиком ИЛИ он выбран сам (например «10.1»)
            part_selected = current_part in wanted
            if part_selected or key in wanted:
                chunks.append(body)
    result = ("===== ОПЕРАЦИОННЫЙ ПРОТОКОЛ АНАЛИТИЧЕСКОГО АГЕНТА BASIS (владелец, v1; общий для всех агентов) =====\n"
              + "".join(chunks).strip()
              + "\n===== КОНЕЦ ПРОТОКОЛА =====\n")
    _cache[ck] = (mtime, result)
    return result


def summary() -> dict:
    text = _read()
    return {"path": PATH, "exists": bool(text), "chars": len(text),
            "core_chars": len(core_text()), "parts": [k for lvl, k, _ in _split(text) if lvl == "part"]}
