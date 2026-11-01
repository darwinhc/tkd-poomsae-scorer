from __future__ import annotations

import socket
from functools import lru_cache
from urllib.parse import urlparse


def _strip_trailing_slash(value: str) -> str:
    return value.rstrip("/")


@lru_cache(maxsize=1)
def detect_server_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass

    try:
        host_name = socket.gethostname()
        ip = socket.gethostbyname(host_name)
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    return "127.0.0.1"


def replace_host_in_base_url(base_url: str, host: str) -> str:
    parsed = urlparse(base_url)
    scheme = parsed.scheme or "http"

    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80

    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if default_port else f"{host}:{port}"

    path = parsed.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def resolve_qr_base_url(
    *,
    configured_base_url: str,
    use_server_ip: bool,
    server_ip_override: str | None,
) -> str:
    if not use_server_ip:
        return _strip_trailing_slash(configured_base_url)

    resolved_ip = server_ip_override.strip() if server_ip_override and server_ip_override.strip() else detect_server_ipv4()
    return _strip_trailing_slash(replace_host_in_base_url(configured_base_url, resolved_ip))
