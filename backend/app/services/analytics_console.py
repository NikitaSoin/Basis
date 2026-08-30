"""Аналитика платформы в одном месте: наш лог + Яндекс.Метрика + Google Search Console.

ЗАЧЕМ (заказ владельца 2026-08-26): «сделать в консоли Basis, чтобы можно было посмотреть
данные Метрики и Search Console по дням/неделе/месяцу, распределение времени, сколько людей
заходило несколько раз, какие страницы — буквами („Рынок: акции“, „Обозреватель: отчёты“) и
агрегированно по блокам».

До этого числа лежали в трёх местах и ни одно не отвечало на вопрос целиком: наш лог знает,
ЧТО человек делал внутри, но не знает, из какого поиска он пришёл; Метрика знает про источник,
но у неё вместо разделов адреса вида `/?view=overview&obs=geo`; Search Console знает про
показы, но её вообще не видно без отдельного скрипта на ноутбуке.

🔴 ГЛАВНОЕ РЕШЕНИЕ — РАЗБОР ПУТЕЙ В ПИТОНЕ, А НЕ В SQL. В консоли уже был готовый запрос с
CASE-лесенкой по path, и он: (1) не покрывал половину случаев (`?view=companies&tab=bonds`,
разделы карточек, `/statistika/`), (2) молча относил непонятое в «прочее», из-за чего блок
«прочее» выглядел вторым по популярности. Лесенку из двадцати WHEN невозможно ни прочитать,
ни расширить. Здесь тот же разбор — обычной функцией с таблицами соответствия: её видно
целиком, дополнить можно одной строкой, а всё неопознанное честно помечается «не разобрано»
вместо того, чтобы прятаться в «прочем».

🔴 ВНЕШНИЕ ИСТОЧНИКИ ДЕГРАДИРУЮТ ЧЕСТНО. Метрике нужен YANDEX_METRIKA_TOKEN, Search Console —
ключ сервисного аккаунта. Ключ лежит в backend/secrets/, а эта папка в .gitignore (репозиторий
публичный) — значит НА СЕРВЕРЕ ЕГО НЕТ, пока владелец не положит его в переменную окружения.
Поэтому оба источника необязательны: нет доступа — блок отвечает «не настроено, вот что
сделать», а не роняет всю страницу. Наш собственный лог работает всегда, он в той же базе.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# ─────────────────────────── названия страниц и блоков ───────────────────────────

# Разделы Обозревателя: ключ из адреса → как называется на экране.
_OBS = {
    "news": "Лента новостей", "economy": "Экономическая статистика", "pulse": "Обзор рынка",
    "maps": "Карта рынка", "calendar": "Календарь", "reports": "Отчёты",
    "corp-news": "Бизнес", "macro": "Макроэкономика", "geo": "Геополитика",
    "institutions": "Институты", "ai": "ИИ-обзор",
}
# Вкладки раздела «Рынок».
_MARKET = {
    "stocks": "акции", "bonds": "облигации", "futures": "фьючерсы", "funds": "фонды",
    "currency": "валюта и металлы", "options": "опционы",
}
# Разделы карточки компании (и SEO-адреса, которые ведут в те же вкладки).
_CARD = {
    "": "обзор", "business": "бизнес-модель", "finance": "финансы",
    "governance": "управление", "markets": "рынки", "macro": "макро",
    "geo": "геополитика", "institutions": "институты", "dividends": "дивиденды",
    "spravedlivaya-tsena": "справедливая цена", "prognoz": "прогноз", "grafik": "график",
    "vyruchka": "выручка", "chistaya-pribyl": "чистая прибыль",
}
# Разделы верхнего уровня по параметру view=.
_VIEW = {
    "companies": "Рынок", "overview": "Обозреватель", "portfolio": "Портфель",
    "stress": "Стресс-тест", "screener": "Скрининг", "ai": "Ассистент",
    "pricing": "Тарифы", "profile": "Профиль",
}


def label(path: str) -> tuple[str, str]:
    """Адрес → («Блок», «Блок: страница»).

    Возвращает ДВА уровня сразу: по первому строится сводка «сколько на блок», по второму —
    подробный список. Неопознанное отдаём как «Не разобрано», чтобы дыру в разборе было
    видно в отчёте, а не размазывало по «прочему».
    """
    if not path:
        return "Не разобрано", "Не разобрано"
    p = str(path).strip()
    base, _, query = p.partition("?")
    base = base.rstrip("/") or "/"
    q = urllib.parse.parse_qs(query)
    get = lambda k: (q.get(k) or [""])[0]

    # Карточка компании: /company/<TICKER>[/<раздел>]
    seg = [s for s in base.split("/") if s]
    if seg and seg[0] == "company":
        if len(seg) == 1:
            return "Карточка компании", "Карточка компании: каталог"
        sec = seg[2] if len(seg) > 2 else ""
        if sec.startswith("otchet"):
            name = "разбор отчётности"
        else:
            name = _CARD.get(sec, sec or "обзор")
        return "Карточка компании", f"Карточка компании: {name}"

    if seg and seg[0] == "bonds":
        return "Облигации", "Облигации: подборка" if len(seg) > 1 and not seg[1].startswith(
            ("RU", "SU", "BY", "XS")) else "Облигации: выпуск"
    if seg and seg[0] == "futures":
        return "Фьючерсы", "Фьючерсы: контракт" if len(seg) > 1 else "Фьючерсы: каталог"
    if seg and seg[0] == "funds":
        return "Фонды", "Фонды: фонд" if len(seg) > 1 else "Фонды: каталог"
    if seg and seg[0] in ("statistika", "pokazateli"):
        n = "макропоказатель" if seg[0] == "statistika" else "термин"
        return "Показатели и термины", f"Показатели и термины: {n}"
    if seg and seg[0] == "indeks":
        return "Индексы", "Индексы: индекс"

    # Разделы приложения: /?view=...&obs=...&tab=...
    view = get("view")
    if view == "overview":
        obs = get("obs")
        return "Обозреватель", f"Обозреватель: {_OBS.get(obs, obs)}" if obs else "Обозреватель: вход"
    if view == "companies":
        tab = get("tab")
        return "Рынок", f"Рынок: {_MARKET.get(tab, tab)}" if tab else "Рынок: вход"
    if view in _VIEW:
        b = _VIEW[view]
        tab = get("tab")
        return b, f"{b}: {tab}" if tab else b
    if base == "/" and not view:
        return "Главная", "Главная"

    # Человекочитаемые лендинги — их много и они разные; в блок сваливаем по общему признаку.
    if seg:
        return "Посадочные страницы", f"Посадочные страницы: /{seg[0]}/"
    return "Не разобрано", f"Не разобрано: {p[:40]}"


# ─────────────────────────────── Яндекс.Метрика ───────────────────────────────

_METRIKA_API = "https://api-metrika.yandex.net/stat/v1/data"


def _http(url: str, headers: dict | None = None, timeout: int = 25):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def metrika(days: int) -> dict:
    """Сводка Метрики за последние `days` дней ВКЛЮЧАЯ сегодняшний.

    🔴 ДАТЫ ЗАДАЁМ ЯВНО, БЕЗ АЛИАСОВ ВРОДЕ «7daysAgo». Владелец 2026-08-29: «смотрю базовые
    цифры в Метрике и то, что в консоли написано как данные Метрики, — они различаются».
    Причина оказалась в периоде: `7daysAgo → today` у API Метрики — это 22–28 августа, то
    есть СЕМЬ ДНЕЙ, ЗАКАНЧИВАЮЩИХСЯ ВЧЕРА (123 визита), а неделя, включающая сегодня, —
    23–29 августа (106 визитов). Наш собственный лог считает от `current_date - N`, то есть
    сегодня включает. Рядом стояли два честных числа за разные недели, и это читалось как
    ошибка. Теперь обе половины страницы меряют один и тот же отрезок, а сам отрезок
    подписан датами — сверять с интерфейсом Метрики можно буквально.

    Робот от человека отделяется параметром isRobot — тем самым, которого нет в интерфейсе
    Метрики, но который отдаёт API (проверено 2026-08-07: 21 робот против 17 людей за день).
    Если роботов за период не было, разница будет нулевой — это не поломка фильтра.
    """
    from datetime import date, timedelta
    _today = date.today()
    date1 = str(_today - timedelta(days=max(0, days - 1)))
    date2 = str(_today)
    token = (os.environ.get("YANDEX_METRIKA_TOKEN") or "").strip()
    counter = os.environ.get("YANDEX_METRIKA_COUNTER", "111213378")
    if not token:
        return {"ok": False, "why": "Нет YANDEX_METRIKA_TOKEN в переменных окружения приложения."}

    def call(filters: str | None = None, dimensions: str | None = None, limit: int = 1):
        p = {"ids": counter, "date1": date1, "date2": date2, "accuracy": "full",
             "metrics": "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,"
                        "ym:s:avgVisitDurationSeconds", "limit": limit}
        if filters:
            p["filters"] = filters
        if dimensions:
            p["dimensions"] = dimensions
            p["sort"] = dimensions
        return _http(f"{_METRIKA_API}?{urllib.parse.urlencode(p)}",
                     {"Authorization": f"OAuth {token}"})

    H = "ym:s:isRobot=='No'"
    try:
        allv = call().get("totals", [0] * 5)
        human = call(H).get("totals", [0] * 5)
        ya = call(f"{H} AND ym:s:searchEngineRoot=='yandex'").get("totals", [0] * 5)
        go = call(f"{H} AND ym:s:searchEngineRoot=='google'").get("totals", [0] * 5)
        organic = call(f"{H} AND ym:s:lastTrafficSource=='organic'").get("totals", [0] * 5)
        direct = call(f"{H} AND ym:s:lastTrafficSource=='direct'").get("totals", [0] * 5)
        days = call(H, "ym:s:date", 60).get("data", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        return {"ok": False, "why": f"Метрика ответила {e.code}: {body}"}
    except Exception as e:  # сеть, таймаут — не роняем всю страницу
        return {"ok": False, "why": f"Метрика недоступна: {type(e).__name__}"}

    return {
        "ok": True, "период": f"{date1} — {date2}",
        "визитов_всего": round(allv[0]), "роботов": round(allv[0] - human[0]),
        "визитов_людей": round(human[0]), "людей": round(human[1]),
        "минут_на_визит": round(human[4] / 60, 1), "глубина": round(human[3], 1),
        "отказы_проц": round(human[2]),
        "из_поиска_визитов": round(organic[0]), "из_поиска_людей": round(organic[1]),
        "яндекс_визитов": round(ya[0]), "яндекс_людей": round(ya[1]),
        "google_визитов": round(go[0]), "google_людей": round(go[1]),
        "прямые_визитов": round(direct[0]), "прямые_людей": round(direct[1]),
        "по_дням": [{"день": d["dimensions"][0]["name"], "визиты": round(d["metrics"][0]),
                     "люди": round(d["metrics"][1]),
                     "минут": round(d["metrics"][4] / 60, 1)} for d in days],
    }


# ────────────────────────── Google Search Console ──────────────────────────

_GSC_API = "https://searchconsole.googleapis.com/webmasters/v3"
_GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def _gsc_key() -> dict | None:
    """Ключ сервисного аккаунта: из переменной окружения либо из файла (локальная разработка).

    🔴 На сервере доступна ТОЛЬКО переменная: backend/secrets/ в .gitignore, потому что
    репозиторий публичный и ключ туда попадать не должен ни при каких обстоятельствах.
    """
    raw = (os.environ.get("GOOGLE_SEARCH_CONSOLE_JSON") or "").strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "secrets", "google-search-console.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
    return None


def _gsc_token(key: dict) -> str:
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    now = int(time.time())
    header = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64(json.dumps({"iss": key["client_email"], "scope": _GSC_SCOPE,
                             "aud": "https://oauth2.googleapis.com/token",
                             "iat": now, "exp": now + 3600}).encode())
    signing = f"{header}.{claims}".encode()
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    private = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    sig = private.sign(signing, padding.PKCS1v15(), hashes.SHA256())
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": f"{header}.{claims}.{b64(sig)}"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())["access_token"]


def gsc(days: int) -> dict:
    """Показы, клики, позиция и топ страниц/запросов из Search Console.

    Google отдаёт данные с задержкой ~2 суток — период считаем от позавчера, иначе хвост
    выглядит нулевым и это читается как провал, которого нет.
    """
    key = _gsc_key()
    if not key:
        return {"ok": False, "why": "Нет ключа Search Console. Положите содержимое "
                                    "google-search-console.json в переменную окружения "
                                    "GOOGLE_SEARCH_CONSOLE_JSON."}
    site = os.environ.get("GSC_SITE", "https://inbasis.ru/")
    from datetime import date, timedelta
    end = date.today() - timedelta(days=2)
    d1, d2 = str(end - timedelta(days=days)), str(end)
    try:
        token = _gsc_token(key)
        def q(dims: list[str], limit: int = 10):
            body = json.dumps({"startDate": d1, "endDate": d2, "dimensions": dims,
                               "rowLimit": limit, "dataState": "all"}).encode()
            req = urllib.request.Request(
                f"{_GSC_API}/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
                data=body, headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode()).get("rows", [])
        tot = q([], 1)
        t = tot[0] if tot else {}
        return {
            "ok": True, "период": f"{d1} — {d2}",
            "показы": round(t.get("impressions", 0)), "клики": round(t.get("clicks", 0)),
            "ctr_проц": round(t.get("ctr", 0) * 100, 2), "позиция": round(t.get("position", 0), 1),
            "по_дням": [{"день": r["keys"][0], "показы": round(r["impressions"]),
                         "клики": round(r["clicks"]), "позиция": round(r["position"], 1)}
                        for r in q(["date"], 60)],
            "страницы": [{"адрес": r["keys"][0].replace(site.rstrip("/"), ""),
                          "показы": round(r["impressions"]), "клики": round(r["clicks"]),
                          "позиция": round(r["position"], 1)} for r in q(["page"], 15)],
            "запросы": [{"запрос": r["keys"][0], "показы": round(r["impressions"]),
                         "клики": round(r["clicks"]), "позиция": round(r["position"], 1)}
                        for r in q(["query"], 15)],
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "why": f"Search Console ответила {e.code}: "
                                    f"{e.read().decode('utf-8', 'replace')[:200]}"}
    except Exception as e:
        return {"ok": False, "why": f"Search Console недоступна: {type(e).__name__}"}
