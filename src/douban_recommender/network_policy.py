from __future__ import annotations

import socket
import urllib.parse
from collections.abc import Callable

from .crawler import MAX_CRAWL_PAGES, normalize_douban_user_id


DEFAULT_SYNC_SAFETY_CAP = MAX_CRAWL_PAGES
DEFAULT_LOCAL_PROXY_PORTS = (7890, 7897, 10809)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def normalize_douban_user(value: str) -> str:
    return normalize_douban_user_id(value)


def normalize_local_proxy_endpoint(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("proxy endpoint must use a loopback host")
    if parsed.scheme.lower() != "http":
        raise ValueError("local proxy endpoint must use the http scheme")
    if not parsed.port:
        raise ValueError("local proxy endpoint must include a port")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("local proxy endpoint must not be a subscription URL")
    return f"http://127.0.0.1:{parsed.port}"


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.12):
            return True
    except OSError:
        return False


def detect_local_http_proxy(
    connect: Callable[[int], bool] | None = None,
    ports: tuple[int, ...] = DEFAULT_LOCAL_PROXY_PORTS,
) -> str:
    probe = connect or _port_is_open
    for port in ports:
        try:
            if probe(int(port)):
                return f"http://127.0.0.1:{int(port)}"
        except OSError:
            continue
    return ""
