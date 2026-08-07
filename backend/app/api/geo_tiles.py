"""Прокси карт-тайлов OpenFreeMap через наш бэкенд.

Причина (2026-08-08, владелец: «карта в геополитике чёрная»): tiles.openfreemap.org
живёт за Cloudflare и из сетей РФ НЕ открывается (TCP к 104.26.x мёртв, DNS местами
отдаёт заглушку) — браузер пользователя не может забрать ни стиль, ни тайлы, MapLibre
рисует пустой чёрный холст. Наш бэкенд на Timeweb до OpenFreeMap ДОСТАЁТ (net-probe:
102 мс) — гоняем трафик через себя.

Механика:
- GET /api/geo/tiles/{path} → https://tiles.openfreemap.org/{path};
- в JSON-ответах (стиль, tilejson) абсолютные ссылки на tiles.openfreemap.org
  переписываются на этот же прокси (адрес берём из заголовков запроса —
  X-Forwarded-Host, адрес API периодически меняется, хардкодить нельзя);
- бинарные ответы (pbf-тайлы, спрайты, глифы) отдаются как есть, с исходными
  Content-Type/Content-Encoding (pbf приходят gzip'ом — НЕ распаковываем);
- кэш в памяти (тайлы иммутабельны) + агрессивный Cache-Control браузеру:
  повторные открытия карт не бьют ни по нам, ни по OpenFreeMap.
"""
from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo/tiles")

_ORIGIN = "https://tiles.openfreemap.org"
_CACHE: dict[str, tuple[bytes, str, str]] = {}  # path -> (body, content_type, content_encoding)
_CACHE_LOCK = threading.Lock()
_CACHE_MAX_ITEMS = 4000          # ~тайлы двух-трёх карт с запасом; тайл 20–300 КБ
_JSON_TYPES = ("application/json", "text/plain")  # tilejson местами text/plain


def _proxy_base(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or "https"
    return f"{proto}://{host}/api/geo/tiles" if host else "/api/geo/tiles"


@router.get("/{path:path}")
def proxy_tile(path: str, request: Request):
    if not path or ".." in path:
        raise HTTPException(status_code=404)
    cached = _CACHE.get(path)
    is_json_rewrite = None  # решаем по факту content-type
    if cached is None:
        req = urllib.request.Request(f"{_ORIGIN}/{path}",
                                     headers={"User-Agent": "inbasis.ru tile proxy"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                cenc = resp.headers.get("Content-Encoding", "")
        except urllib.error.HTTPError as e:
            raise HTTPException(status_code=e.code)
        except Exception:  # noqa: BLE001
            logger.warning("geo_tiles: origin недоступен для %s", path)
            raise HTTPException(status_code=502, detail="источник тайлов недоступен")
        with _CACHE_LOCK:
            if len(_CACHE) >= _CACHE_MAX_ITEMS:
                _CACHE.clear()  # простой сброс: иммутабельные тайлы дозакачаются
            _CACHE[path] = (body, ctype, cenc)
        cached = (body, ctype, cenc)
    body, ctype, cenc = cached
    is_json_rewrite = any(t in ctype for t in _JSON_TYPES)
    headers = {"Cache-Control": "public, max-age=604800, immutable"}
    if is_json_rewrite:
        # стиль/tilejson: ссылки на origin -> наш прокси (адрес из запроса)
        try:
            txt = body.decode("utf-8")
            txt = txt.replace(_ORIGIN, _proxy_base(request))
            return Response(content=txt, media_type="application/json", headers=headers)
        except Exception:  # noqa: BLE001
            pass
    if cenc:
        headers["Content-Encoding"] = cenc
    return Response(content=body, media_type=ctype, headers=headers)
