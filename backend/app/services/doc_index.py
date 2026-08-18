"""Поисковый слой по ПРОЗЕ платформы (retrieval для ассистента).

Зачем: аналитика Basis живёт не только в таблицах, но и в тысячах текстов —
разборы вкладок карточек (бизнес-модель, финансы, управление, рынки, макро,
гео, институты), досье эмитентов облигаций, разборы выпусков/фондов/фьючерсов,
методички. Ассистент до этого видел ПЯТЬ обрезанных файлов по тикеру и ничего
больше: вопрос «что вы писали про замещающие облигации» отвечать было нечем.

Почему лексический индекс, а не эмбеддинги:
  1. Эмбеддинги требуют внешнего API на КАЖДЫЙ документ и на каждый запрос —
     у инстанса egress к провайдерам режется (см. память про DeepSeek/FRED),
     а ещё это деньги и отдельный сторедж векторов;
  2. корпус узкий и терминологичный (тикеры, названия эмитентов, «дюрация»,
     «оферта», «замещающие») — BM25 по словам здесь работает предсказуемо;
  3. всё живёт в файлах, которые едут в образ вместе с бэкендом, — не нужна
     ни миграция, ни синхронизация.

Память: в индексе НЕ хранится текст, только счётчики частот по документу
(top-N токенов). Полный текст читается с диска в момент выдачи фрагмента.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from array import array
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent.parent

# Что индексируем: (папка, тип сущности). Внутри — <ID>/<файл>.md
_ROOTS = [
    (BACKEND_DIR / "companies", "company"),
    (BACKEND_DIR / "bond_issuers", "bond_issuer"),
    (BACKEND_DIR / "bonds", "bond"),
    (BACKEND_DIR / "funds", "fund"),
    (BACKEND_DIR / "futures", "future"),
]
# Плоские папки с методичками — сущности нет, есть тема
_FLAT_ROOTS = [
    (BACKEND_DIR / "docs", "doc"),
    (BACKEND_DIR / "knowledge", "doc"),
]

# ВНУТРЕННИЕ файлы контроля качества — в выдачу ассистента не идут: это
# служебная переписка о карточке (замечания критика, отзыв персоны, red-team),
# а не аналитика для инвестора. Показать их пользователю — значит выдать
# черновик за вывод.
_SKIP_FILES = {"critic_review.md", "persona_feedback.md", "geo_redteam.md",
               "fact_check.md", "critic_notes.md"}

_MAX_DOCS = 12000            # предохранитель: корпус вырос — не съедаем память молча
_TOP_TOKENS_PER_DOC = 260    # столько самых частых токенов документа держим в индексе
_MAX_FILE_BYTES = 400_000    # файлы крупнее читаем частично (у прозы столько не бывает)

# Человеческие названия разделов — попадают в выдачу, чтобы ассистент понимал,
# ЧТО он нашёл, и мог сослаться понятно для пользователя.
KIND_TITLES = {
    "business_model": "Бизнес-модель",
    "financials_summary": "Финансы и оценка",
    "governance_summary": "Корпоративное управление",
    "market_summary": "Рынки компании",
    "macro_summary": "Макроэкономика компании",
    "geo_summary": "Геополитика компании",
    "institutions_summary": "Институты компании",
    "bond_risk": "Долговая нагрузка эмитента",
    "analysis_summary": "Разбор аналитика",
    "business": "Бизнес эмитента",
    "financials": "Финансы эмитента",
}

_STOP = {
    "это", "как", "что", "для", "или", "все", "его", "их", "она", "они", "оно", "при",
    "над", "под", "про", "так", "уже", "еще", "ещё", "быть", "был", "была", "было",
    "были", "есть", "нет", "если", "чем", "чтобы", "который", "которая", "которые",
    "года", "году", "год", "млрд", "млн", "тыс", "руб", "рублей", "the", "and", "for",
}

_TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _norm(tok: str) -> str:
    """Грубая нормализация вместо морфологии: режем длинные слова до 6 символов,
    чтобы «облигация/облигации/облигациям» сходились в один ключ. Для корпуса из
    терминов и имён этого достаточно, а pymorphy тянуть в образ ради поиска —
    лишняя зависимость."""
    return tok[:6] if len(tok) > 6 else tok


def _tokens(text: str) -> list[str]:
    out = []
    for m in _TOKEN_RE.finditer(text.lower()):
        t = m.group(0)
        if len(t) < 3 or t in _STOP:
            continue
        out.append(_norm(t))
    return out


def _title_of(path: Path, text: str) -> str:
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:120]
    return path.stem


class _Index:
    """Инвертированный индекс: токен → списки (документ, частота).

    Держать частоты ПО ДОКУМЕНТУ (словарь на каждый документ) стоило 73 МБ RSS на
    корпусе в 3211 файлов — на инстансе это заметная доля памяти процесса, да ещё
    и на каждый воркер. Постинг-списки в array('i') хранят те же данные компактно,
    а поиск при этом становится быстрее: трогаем только документы, где слово
    вообще есть, а не все подряд.
    """

    def __init__(self):
        self.docs: list[dict] = []          # {id, path, entity, entity_kind, kind, title}
        self.postings: dict[str, tuple] = {}  # token -> (array docs, array tf)
        self.lens: list[int] = []
        self.df: Counter = Counter()
        self.built_at: float = 0.0
        self.avg_len: float = 1.0


_INDEX = _Index()
_LOCK = threading.Lock()
_TTL = 6 * 3600.0


def _iter_files():
    for root, entity_kind in _ROOTS:
        if not root.is_dir():
            continue
        for entity_dir in sorted(root.iterdir()):
            if not entity_dir.is_dir():
                continue
            for f in sorted(entity_dir.glob("*.md")):
                if f.name in _SKIP_FILES:
                    continue
                yield f, entity_dir.name, entity_kind
    for root, entity_kind in _FLAT_ROOTS:
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*.md")):
            if f.name in _SKIP_FILES:
                continue
            yield f, f.stem, entity_kind


def _build() -> None:
    t0 = time.time()
    idx = _Index()
    acc: dict[str, list] = {}   # token -> [docs, tfs] (собираем, потом ужимаем в array)
    for f, entity, entity_kind in _iter_files():
        if len(idx.docs) >= _MAX_DOCS:
            logger.warning("doc_index: корпус превысил %d документов — индексируем частично", _MAX_DOCS)
            break
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")[:_MAX_FILE_BYTES]
        except OSError:
            continue
        if len(text.strip()) < 60:
            continue
        toks = _tokens(text)
        if not toks:
            continue
        cnt = Counter(toks)
        kept = cnt.most_common(_TOP_TOKENS_PER_DOC)
        doc_id = len(idx.docs)
        idx.docs.append({
            "id": doc_id,
            "path": str(f.relative_to(BACKEND_DIR)),
            "entity": entity,
            "entity_kind": entity_kind,
            "kind": f.stem,
            "title": _title_of(f, text),
        })
        idx.lens.append(len(toks))
        for tok, tf in kept:
            slot = acc.get(tok)
            if slot is None:
                slot = acc[tok] = [[], []]
            slot[0].append(doc_id)
            slot[1].append(min(tf, 65535))
            idx.df[tok] += 1
    idx.postings = {tok: (array("i", d), array("H", t)) for tok, (d, t) in acc.items()}
    acc.clear()
    idx.avg_len = (sum(idx.lens) / len(idx.lens)) if idx.lens else 1.0
    idx.built_at = time.time()
    globals()["_INDEX"] = idx
    logger.info("doc_index: построен за %.1f с — %d документов, %d уникальных токенов",
                time.time() - t0, len(idx.docs), len(idx.df))


def ensure_index(force: bool = False) -> _Index:
    idx = _INDEX
    if not force and idx.docs and time.time() - idx.built_at < _TTL:
        return idx
    with _LOCK:
        idx = _INDEX
        if force or not idx.docs or time.time() - idx.built_at >= _TTL:
            _build()
        return _INDEX


def stats() -> dict:
    idx = ensure_index()
    by_kind = Counter(d["entity_kind"] for d in idx.docs)
    return {"docs": len(idx.docs), "tokens": len(idx.df), "avg_len": round(idx.avg_len, 1),
            "built_at": idx.built_at, "by_entity_kind": dict(by_kind)}


def _snippet(path: Path, q_tokens: set[str], width: int = 420) -> str:
    """Фрагмент вокруг самого «плотного» по запросу места документа."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:_MAX_FILE_BYTES]
    except OSError:
        return ""
    words = list(_TOKEN_RE.finditer(text.lower()))
    if not words:
        return text[:width]
    best_pos, best_hits = 0, -1
    step = 25
    for i in range(0, len(words), step):
        window = words[i:i + 60]
        hits = sum(1 for m in window if _norm(m.group(0)) in q_tokens)
        if hits > best_hits:
            best_hits, best_pos = hits, window[0].start() if window else 0
    start = max(0, best_pos - 60)
    frag = text[start:start + width].strip().replace("\n", " ")
    return ("…" if start else "") + frag + ("…" if start + width < len(text) else "")


def search(query: str, *, entity: str | None = None, entity_kind: str | None = None,
           kind: str | None = None, limit: int = 6) -> list[dict]:
    """BM25 по корпусу прозы. entity — тикер/SECID/слаг эмитента (фильтр),
    entity_kind — company|bond_issuer|bond|fund|future|doc, kind — имя раздела."""
    idx = ensure_index()
    q = [t for t in _tokens(query)]
    if not q or not idx.docs:
        return []
    qset = set(q)
    N = len(idx.docs)
    k1, b = 1.4, 0.75
    ent = entity.upper() if entity else None
    # BM25 по постинг-спискам: перебираем только документы, где слово встречается
    acc: dict[int, float] = {}
    for tok in qset:
        posting = idx.postings.get(tok)
        if not posting:
            continue
        docs_arr, tf_arr = posting
        idf = math.log(1 + (N - idx.df.get(tok, 1) + 0.5) / (idx.df.get(tok, 1) + 0.5))
        for j, doc_id in enumerate(docs_arr):
            tf = tf_arr[j]
            dl = idx.lens[doc_id] or 1
            acc[doc_id] = acc.get(doc_id, 0.0) + idf * (tf * (k1 + 1)) / (
                tf + k1 * (1 - b + b * dl / idx.avg_len))
    scored: list[tuple[float, int]] = []
    for doc_id, s in acc.items():
        doc = idx.docs[doc_id]
        if ent and doc["entity"].upper() != ent:
            continue
        if entity_kind and doc["entity_kind"] != entity_kind:
            continue
        if kind and doc["kind"] != kind:
            continue
        scored.append((s, doc_id))
    scored.sort(reverse=True)
    out = []
    for s, i in scored[:limit]:
        doc = idx.docs[i]
        out.append({
            "doc_id": doc["path"],
            "entity": doc["entity"],
            "entity_kind": doc["entity_kind"],
            "section": KIND_TITLES.get(doc["kind"], doc["kind"]),
            "title": doc["title"],
            "score": round(s, 2),
            "snippet": _snippet(BACKEND_DIR / doc["path"], qset),
        })
    return out


def read_doc(doc_id: str, max_chars: int = 6000) -> dict:
    """Читает документ целиком по doc_id из выдачи search (путь относительно
    backend/). Путь проверяется на выход за корпус — doc_id приходит из ответа
    модели, то есть это недоверенный ввод."""
    p = (BACKEND_DIR / doc_id).resolve()
    roots = [r.resolve() for r, _ in _ROOTS] + [r.resolve() for r, _ in _FLAT_ROOTS]
    if not any(str(p).startswith(str(r)) for r in roots) or p.suffix != ".md":
        return {"error": "документ вне корпуса платформы"}
    if p.name in _SKIP_FILES or not p.is_file():
        return {"error": "документ не найден"}
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"error": "документ не читается"}
    return {"doc_id": doc_id, "title": _title_of(p, text), "chars": len(text),
            "truncated": len(text) > max_chars, "text": text[:max_chars]}
