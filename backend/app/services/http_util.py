"""HTTP-клиент с клампингом TCP MSS — обход MTU black hole на маршруте инстанса.

К части внешних хостов (api.deepseek.com, api.stlouisfed.org/FRED) TLS-рукопожатие
виснет: TCP-коннект проходит, а крупные пакеты (сертификат сервера, ~3-5 КБ) молча
теряются из-за битого Path MTU на сетевом пути инстанса (ICMP «нужна фрагментация»
режется). Уменьшение TCP MSS заставляет сервер слать мелкие сегменты, которые
проходят узкое место → рукопожатие завершается.

Это лечение на НАШЕЙ стороне, без прокси. Размер MSS настраивается переменной
окружения TCP_MSS_CLAMP (по умолчанию 1200; типичный «узкий» путь — 1400, берём с
запасом). Клампинг безвреден для нормальных маршрутов — просто чуть мельче сегменты.
"""
import os
import socket

import httpx


def _mss() -> int:
    try:
        return int(os.environ.get("TCP_MSS_CLAMP", "1200"))
    except ValueError:
        return 1200


def _socket_options():
    # TCP_MAXSEG есть на Linux (бой — Linux). На платформах без него — без клампинга.
    if hasattr(socket, "TCP_MAXSEG"):
        return [(socket.IPPROTO_TCP, socket.TCP_MAXSEG, _mss())]
    return None


def make_client(timeout=None, headers=None) -> httpx.Client:
    """httpx.Client с клампингом MSS на сокете (обход MTU black hole)."""
    transport = httpx.HTTPTransport(retries=0, socket_options=_socket_options())
    return httpx.Client(timeout=timeout, headers=headers or {}, transport=transport)
