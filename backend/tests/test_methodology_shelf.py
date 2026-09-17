"""Контракт полки методичек.

🔴 Зачем: методичка подключается ДВУМЯ независимыми действиями — файл кладут в
`docs/`, а её id вписывают в `shelf_docs` агента. Любое из двух можно забыть, и
отказ будет тихим: полка честно напишет «⚠ НЕДОСТУПНА» внутри системного
промпта, агент пожмёт плечами и напишет разбор «по своей странной логике» —
ровно то, против чего этот слой и строился. Ни тесты, ни витрина этого не
покажут.

В памяти проекта такой случай уже записан: методичка была не в git, и «работает»
оказалось ложным — на бою файла не было.
"""
import re
from pathlib import Path

import pytest

from app.services.methodology import REGISTRY, outline, read_section, shelf_card

SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"


@pytest.mark.parametrize("doc_id", sorted(REGISTRY))
def test_файл_методички_на_месте(doc_id):
    """Файл существует и читается — иначе полка отдаёт агенту «НЕДОСТУПНА»."""
    doc = REGISTRY[doc_id]
    assert Path(doc.path).exists(), f"{doc_id}: нет файла {doc.filename} (забыли git add?)"
    info = outline(doc_id)
    assert not info.get("error"), f"{doc_id}: {info.get('error')}"
    assert info["разделов"] >= 5, f"{doc_id}: всего {info['разделов']} разделов — похоже на обрубок"


@pytest.mark.parametrize("doc_id", sorted(REGISTRY))
def test_разделы_адресуемы(doc_id):
    """Раздел из оглавления обязан открываться по своему же имени.

    Ловит расхождение парсера с разметкой документа: агент видит раздел в
    оглавлении, а открыть не может — и молча идёт рассуждать сам."""
    items = outline(doc_id)["оглавление"]
    # Разметка методичек разная: часть пронумерована («2.4», «Часть 3»), часть —
    # только заголовками (geo). Полка умеет и то и другое, поэтому и проверяем
    # обоими способами: иначе тест либо падает на законном документе, либо
    # молча проверяет ноль разделов.
    checked = 0
    for item in items[:40]:
        name = str(item["раздел"])
        got = read_section(doc_id, name)
        assert not got.get("error"), (
            f"{doc_id}: раздел «{name}» есть в оглавлении, но открыть его нельзя")
        checked += 1
    assert checked >= 5, f"{doc_id}: проверено всего {checked} разделов"


@pytest.mark.parametrize("doc_id", sorted(REGISTRY))
def test_у_методички_есть_когда_открывать(doc_id):
    """`when_to_use` — единственное, по чему агент выбирает документ. Короткая
    отписка вроде «про институты» отправляет его не туда."""
    doc = REGISTRY[doc_id]
    assert len(doc.when_to_use) >= 120, f"{doc_id}: описание «когда открывать» слишком куцее"
    assert doc.title, f"{doc_id}: нет названия"


def test_агенты_ссылаются_только_на_существующие_методички():
    """Второй конец подключения: id в shelf_docs агента должен быть на полке.

    Опечатка в id не падает — полка просто пропускает документ, и агент теряет
    методичку, не узнав об этом."""
    pattern = re.compile(r"shelf_docs\s*=\s*\[(.*?)\]|shelf_card\(\s*\[(.*?)\]", re.S)
    seen: dict[str, set[str]] = {}
    for path in SERVICES.glob("*.py"):
        if path.name == "methodology.py":
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            body = match.group(1) or match.group(2) or ""
            ids = set(re.findall(r'"([a-z_]+)"', body))
            if ids:
                seen.setdefault(path.name, set()).update(ids)
    assert seen, "не нашли ни одного потребителя полки — проверьте регулярное выражение"
    unknown = {f: sorted(ids - set(REGISTRY)) for f, ids in seen.items() if ids - set(REGISTRY)}
    assert not unknown, f"ссылки на несуществующие методички: {unknown}"


def test_новые_методички_розданы_потребителям():
    """Регистрация без раздачи бессмысленна: документ на полке, но ни один агент
    его не видит. Проверяем, что каждый id кому-то выдан."""
    # ALL_SHELF (handoffs.py) — тоже раздача: его целиком получают три аналитика сводок,
    # перекрёстный опрос и совет; документ, добавленный только туда, выдан всем.
    pattern = re.compile(r"shelf_docs\s*=\s*\[(.*?)\]|shelf_card\(\s*\[(.*?)\]|ALL_SHELF\s*=\s*\[(.*?)\]", re.S)
    handed: set[str] = set()
    for path in SERVICES.glob("*.py"):
        if path.name == "methodology.py":
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            handed.update(re.findall(r'"([a-z_]+)"', match.group(1) or match.group(2) or match.group(3) or ""))
    orphans = sorted(set(REGISTRY) - handed)
    assert not orphans, f"методички на полке, но никому не выданы: {orphans}"


def test_карточка_полки_не_кричит_о_недоступности():
    card = shelf_card()
    assert "НЕДОСТУПНА" not in card, "полка отдаёт агенту методичку-пустышку"
    assert len(card) < 30_000, "карточка полки распухла — агент получит стену текста"


def test_часть_открывается_целиком():
    """До 2026-09-14 «Часть 8» отдавала 51 знак — обложку без подразделов."""
    got = read_section("geo_base", "Часть 8")
    assert not got.get("error") and len(got["текст"]) > 8000
    assert got["подразделов"] >= 20 and got["вошли"] and "8.1" in {i["раздел"] for i in got["вошли"]}
    small = read_section("code", "Часть 2")
    assert not small.get("error") and "Типовые ошибки" in small["название"]


def test_буквенный_суффикс_номера_различается():
    a, b = read_section("geo_base", "8.17"), read_section("geo_base", "8.17а")
    assert a["раздел"] == "8.17" and b["раздел"] == "8.17а" and len(b["текст"]) > len(a["текст"])
    ids = [str(i["раздел"]) for i in outline("geo_base")["оглавление"]]
    assert len(ids) == len(set(ids)), "дубли номеров в оглавлении"


def test_карточка_полки_с_названиями_частей():
    card = shelf_card(["geo_base"])
    assert "Модуль анализа вооружённого конфликта" in card and "8.1–8.30" in card
    from app.services.handoffs import ALL_SHELF
    assert len(shelf_card(ALL_SHELF)) < 30_000
