#!/usr/bin/env python3
"""Генератор статических SEO-страниц компаний (build/company/<TICKER>/index.html).

Проблема: приложение — client-side SPA без роутинга (все разделы живут на "/" как
состояние вкладок), боты видят пустой HTML-шелл. Полноценный SSR недоступен — фронт
и бэк на РАЗНЫХ доменах (inbasis.ru vs API), деплой фронта — закоммиченный build/,
не пересборка на сервере. Поэтому вместо server-side rendering — build-time генерация
лёгких, но РЕАЛЬНЫХ статических страниц по данным из companies/<TICKER>/financials.json:
title/description под конкретный тикер + читаемый факт-лист + переход в живое
приложение. Каждая страница — самостоятельный HTML без React, ничего не рендерит SPA.

Запускается ПОСЛЕ `craco build` (см. вызов в package.json/CI), пишет в build/company/.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_COMPANIES_DIR = os.path.join(_ROOT, "backend", "companies")
_RATES_CSV = os.path.join(_ROOT, "rates.csv")
_BUILD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build")
_SITE = "https://inbasis.ru"


def _load_names() -> dict[str, str]:
    """SECID -> человекочитаемое название компании из rates.csv (справочник тикеров)."""
    names = {}
    if not os.path.exists(_RATES_CSV):
        return names
    with open(_RATES_CSV, encoding="cp1251") as f:
        reader = csv.reader(f, delimiter=";")
        header = None
        for row in reader:
            if not row or not row[0].strip():
                continue
            if row[0] == "SECID":
                header = row
                continue
            if header is None:
                continue
            d = dict(zip(header, row))
            secid = d.get("SECID", "").strip()
            name = (d.get("EMITENTNAME") or d.get("NAME") or "").strip()
            if secid and name:
                names[secid] = name
    return names


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _company_facts(ticker: str) -> dict | None:
    path = os.path.join(_COMPANIES_DIR, ticker, "financials.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data


def _render_page(ticker: str, name: str, facts: dict) -> str:
    key_facts = facts.get("key_facts") or []
    rows = "".join(
        f"<tr><th>{html.escape(_strip(kf.get('label', '')))}</th>"
        f"<td>{html.escape(_strip(kf.get('value', '')))}</td></tr>"
        for kf in key_facts if kf.get("label") and kf.get("value")
    )
    name_esc = html.escape(name)
    title = f"{name_esc} ({ticker}): анализ, справедливая цена, финансовые показатели | Basis"
    desc = html.escape(
        f"{name} ({ticker}) на Мосбирже — независимый разбор Basis: ключевые факты, "
        f"финансовые показатели, оценка. Не брокер, без сигналов «купить/продать»."
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{_SITE}/company/{ticker}/">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{_SITE}/company/{ticker}/">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:40px auto;
     padding:0 20px;color:#1a1a1a;line-height:1.5}}
h1{{font-size:22px}} table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{text-align:left;padding:8px 4px;border-bottom:1px solid #eee;font-size:14px}}
th{{color:#666;font-weight:500;width:40%}}
a.cta{{display:inline-block;margin-top:16px;padding:10px 20px;background:#4F5BD5;color:#fff;
      text-decoration:none;border-radius:6px;font-size:14px}}
p.note{{font-size:12px;color:#999;margin-top:24px}}
</style>
</head>
<body>
<h1>{name_esc} ({ticker})</h1>
<p>Независимый разбор Basis по бумаге {ticker} на Московской бирже. Ниже — ключевые факты
по компании; полная аналитика (финансы, оценка, управление, макро, геополитика) — в приложении.</p>
{f'<table>{rows}</table>' if rows else ''}
<a class="cta" href="{_SITE}/?company={ticker}">Открыть полный разбор в Basis →</a>
<p class="note">Basis — не брокер, не даёт торговых сигналов. Это независимый аналитический
слой: факты, оценки и логика для собственного решения инвестора.</p>
</body>
</html>"""


def _write_sitemap(tickers: list[str]) -> None:
    """Тот же список тикеров, что реально получил страницу — источник правды один
    (генератор), не дублируем его вручную в отдельном sitemap.xml."""
    urls = [f"  <url><loc>{_SITE}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for t in tickers:
        urls.append(f"  <url><loc>{_SITE}/company/{t}/</loc>"
                    f"<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    with open(os.path.join(_BUILD_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(xml)


def main() -> None:
    if not os.path.isdir(_COMPANIES_DIR):
        print("companies dir не найден — пропуск")
        return
    names = _load_names()
    written_tickers = []
    skipped = []
    for ticker in sorted(os.listdir(_COMPANIES_DIR)):
        if ticker.startswith("_") or ticker in ("ocr2025",):
            continue
        facts = _company_facts(ticker)
        if facts is None:
            skipped.append(ticker)
            continue
        name = names.get(ticker, ticker)
        page_html = _render_page(ticker, name, facts)
        out_dir = os.path.join(_BUILD_DIR, "company", ticker)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page_html)
        written_tickers.append(ticker)
    _write_sitemap(written_tickers)
    print(f"SEO-страницы компаний: записано {len(written_tickers)}, пропущено "
          f"(нет financials.json) {len(skipped)}; sitemap.xml обновлён "
          f"({len(written_tickers) + 1} URL)")
    if skipped:
        print("пропущены:", ", ".join(skipped[:20]), "..." if len(skipped) > 20 else "")


if __name__ == "__main__":
    main()
