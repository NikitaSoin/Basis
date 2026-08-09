"""Мост «макро → сектор → бизнес компании»: выдача кусков методички под задачу.

🔴 ЗАЧЕМ (владелец, 2026-08-09): «закинул методичку, как макроэкономика влияет на
сектора. Нужно, чтобы агент строил секторальное влияние в оценке макроэкономики по ней,
и чтобы агент, который меняет карточки компаний, тоже на неё опирался».

Методичка (`docs/macro_to_business_sectors.md`, ~1650 строк) целиком в промпт не лезет
и не нужна целиком: у выпуска Обозревателя задача одна — держать общий каркас и
секторные чувствительности, у патчера карточки другая — знать ОДИН сектор глубоко.
Поэтому здесь разбор документа на части и две выдачи:

  core()             — каркас: цепочка трансмиссии, типы индикаторов, сквозные
                       драйверы с якорями, сводная таблица чувствительностей,
                       чек-лист ошибок. Идёт в макро-выпуск.
  for_sector(имя)    — блоки ЧАСТИ 3 по конкретному сектору платформы. Идут в патчер
                       карточки и в любой per-company контур.

Отдельный модуль, а не текст в промпте, по двум причинам: (1) методичку правит владелец
в docs/, и она обязана доезжать до бота без правки кода; (2) один разбор на процесс —
дешевле, чем читать 125 КБ на каждый прогон.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PATH = os.path.join(_REPO, "docs", "macro_to_business_sectors.md")

# Сектор платформы (companies.sector — 13 чистых значений, см. память проекта) →
# номера разделов ЧАСТИ 3. Соответствие НЕ один-к-одному: у методички 20 секторов,
# у платформы 13, и это правильно — «Металлургия» на бирже одна, а чёрная, цветная и
# уголь живут по разным драйверам, поэтому агенту отдаём все три блока.
SECTOR_MAP: dict[str, tuple[str, ...]] = {
    "Нефть и газ": ("3.2",),
    "Металлургия": ("3.3", "3.4", "3.5"),
    "Финансы": ("3.1", "3.17", "3.18"),
    "Потребительский сектор": ("3.6", "3.7", "3.8", "3.15"),
    "IT-сектор": ("3.9", "3.10"),
    "Телеком": ("3.11",),
    "Электроэнергетика": ("3.12",),
    "Химия": ("3.13",),
    "Транспорт и логистика": ("3.14",),
    "Здравоохранение": ("3.16",),
    "Девелопмент": ("3.19",),
    "Машиностроение": ("3.20",),
    "Прочее": (),
}

# Части, из которых собирается каркас. ЧАСТЬ 5 (источники данных) и ЧАСТЬ 6 (фискальный
# блок) намеренно НЕ здесь: первая — инструкция человеку, откуда тянуть ряды, вторая
# нужна точечно и раздувает промпт выпуска.
_CORE_PARTS = ("0", "1", "2", "4", "7")

_cache: dict | None = None


def _parse() -> dict:
    """Разбор файла на части и секторные блоки. Кэш на процесс."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(PATH, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        logger.warning("sector-playbook: методичка недоступна (%s): %s", PATH, e)
        _cache = {"ok": False, "parts": {}, "sectors": {}}
        return _cache

    parts: dict[str, str] = {}
    # Заголовки вида «# ЧАСТЬ 3. СЕКТОРЫ» — режем по ним, номер части в ключ.
    chunks = re.split(r"^#\s+ЧАСТЬ\s+(\d+)\.", text, flags=re.M)
    # chunks: [преамбула, "0", текст0, "1", текст1, ...]
    for i in range(1, len(chunks) - 1, 2):
        parts[chunks[i]] = chunks[i + 1].strip()

    sectors: dict[str, dict] = {}
    part3 = parts.get("3", "")
    blocks = re.split(r"^##\s+(3\.\d+)\.\s*(.+)$", part3, flags=re.M)
    for i in range(1, len(blocks) - 2, 3):
        num, title, body = blocks[i], blocks[i + 1].strip(), blocks[i + 2].strip()
        sectors[num] = {"title": title, "text": body}

    _cache = {"ok": bool(parts and sectors), "parts": parts, "sectors": sectors,
              "path": PATH}
    logger.info("sector-playbook: разобрано частей %d, секторов %d", len(parts), len(sectors))
    return _cache


def available() -> dict:
    """Диагностика: доехала ли методичка до рантайма и что в ней нашлось."""
    data = _parse()
    return {"ok": data["ok"], "path": data.get("path"),
            "parts": sorted(data["parts"].keys()),
            "sectors": {k: v["title"] for k, v in sorted(data["sectors"].items())}}


def core(max_chars: int = 45000) -> str:
    """Каркас моста «макро → сектор» для выпуска Обозревателя."""
    data = _parse()
    if not data["ok"]:
        return ""
    out = ["=== МЕТОДИЧКА «МАКРО → СЕКТОР» (каркас; полная версия у владельца в docs) ==="]
    for num in _CORE_PARTS:
        body = data["parts"].get(num)
        if body:
            out.append(f"\n--- ЧАСТЬ {num} ---\n{body}")
    text = "\n".join(out)
    return text[:max_chars]


def for_sector(sector: str | None, max_chars: int = 20000) -> str:
    """Блоки ЧАСТИ 3 под сектор платформы. Пусто — сектора нет в карте (это не ошибка:
    «Прочее» и незнакомые значения честно остаются без секторного блока)."""
    data = _parse()
    if not data["ok"] or not sector:
        return ""
    nums = SECTOR_MAP.get(sector.strip())
    if nums is None:
        # Незнакомое имя — пробуем по вхождению, чтобы переименование сектора в БД
        # не отключало мост молча.
        for key, val in SECTOR_MAP.items():
            if key.lower()[:6] in sector.lower():
                nums = val
                break
    if not nums:
        return ""
    out = [f"=== МЕТОДИЧКА «МАКРО → СЕКТОР»: {sector} ==="]
    for num in nums:
        blk = data["sectors"].get(num)
        if blk:
            out.append(f"\n--- {num}. {blk['title']} ---\n{blk['text']}")
    return "\n".join(out)[:max_chars]
