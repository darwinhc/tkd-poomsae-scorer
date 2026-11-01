from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from threading import Lock
from time import time
from urllib.parse import quote

from fastapi import Request

INTERNAL_ADMIN_BASE_PATH = "/admin"
_LOGIN_ATTEMPTS_LOCK = Lock()
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_LOCKED_UNTIL: dict[str, float] = {}


@dataclass(frozen=True)
class LoginFailureResult:
    attempts: int
    locked: bool
    lock_seconds_remaining: int


def normalize_admin_base_path(raw_value: str | None) -> str:
    raw = (raw_value or "").strip()
    if not raw:
        return INTERNAL_ADMIN_BASE_PATH
    if not raw.startswith("/"):
        raw = f"/{raw}"
    normalized = raw.rstrip("/")
    if not normalized:
        return INTERNAL_ADMIN_BASE_PATH
    if normalized == "/":
        return INTERNAL_ADMIN_BASE_PATH
    return normalized


def to_internal_admin_path(path: str, *, configured_base_path: str) -> str:
    base = normalize_admin_base_path(configured_base_path)
    if base == INTERNAL_ADMIN_BASE_PATH:
        return path
    if path == base:
        return INTERNAL_ADMIN_BASE_PATH
    if path.startswith(f"{base}/"):
        suffix = path[len(base) :]
        return f"{INTERNAL_ADMIN_BASE_PATH}{suffix}"
    return path


def to_external_admin_path(path: str, *, configured_base_path: str) -> str:
    base = normalize_admin_base_path(configured_base_path)
    if base == INTERNAL_ADMIN_BASE_PATH:
        return path
    if path == INTERNAL_ADMIN_BASE_PATH:
        return base
    if path.startswith(f"{INTERNAL_ADMIN_BASE_PATH}/"):
        suffix = path[len(INTERNAL_ADMIN_BASE_PATH) :]
        return f"{base}{suffix}"
    return path


def is_internal_admin_path(path: str) -> bool:
    return path == INTERNAL_ADMIN_BASE_PATH or path.startswith(f"{INTERNAL_ADMIN_BASE_PATH}/")


def is_admin_auth_enabled(request: Request) -> bool:
    raw = request.app.state.settings.admin_password
    return bool(isinstance(raw, str) and raw.strip())


def build_admin_auth_token(*, password: str, secret_key: str) -> str:
    base = f"{password}::{secret_key}::admin"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def is_admin_authenticated(request: Request) -> bool:
    if not is_admin_auth_enabled(request):
        return True
    settings = request.app.state.settings
    cookie_value = request.cookies.get(settings.admin_auth_cookie_name)
    if not cookie_value:
        return False
    expected = build_admin_auth_token(
        password=settings.admin_password,
        secret_key=settings.jwt_secret_key,
    )
    return hmac.compare_digest(cookie_value, expected)


def is_internal_public_admin_path(path: str) -> bool:
    if path in (f"{INTERNAL_ADMIN_BASE_PATH}/login", f"{INTERNAL_ADMIN_BASE_PATH}/logout"):
        return True
    return False


def is_internal_live_admin_path(path: str) -> bool:
    if path.startswith(f"{INTERNAL_ADMIN_BASE_PATH}/stations/") and (
        path.endswith("/scoreboard") or path.endswith("/scoreboard/live")
    ):
        return True
    return False


def login_redirect_url(*, request: Request, external_next_path: str | None = None) -> str:
    settings = request.app.state.settings
    external_base = normalize_admin_base_path(settings.admin_base_path)
    next_path = external_next_path or external_base
    return f"{external_base}/login?next={quote(next_path, safe='/?=&')}"


def normalize_next_path(*, next_value: str | None, configured_base_path: str) -> str:
    base = normalize_admin_base_path(configured_base_path)
    if not next_value:
        return base
    if next_value == base or next_value.startswith(f"{base}/"):
        return next_value
    return base


def get_client_ip(request: Request) -> str:
    trust_proxy = bool(getattr(request.app.state.settings, "admin_trust_proxy_headers", False))
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _parse_allowlist(raw_value: str | None) -> list[str]:
    raw = (raw_value or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def is_ip_allowed(request: Request) -> bool:
    settings = request.app.state.settings
    allowlist = _parse_allowlist(settings.admin_ip_allowlist)
    if not allowlist:
        return True

    client_ip = get_client_ip(request)
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for item in allowlist:
        try:
            if "/" in item:
                network = ipaddress.ip_network(item, strict=False)
                if ip_obj in network:
                    return True
            elif ip_obj == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def get_login_lock_seconds_remaining(request: Request) -> int:
    client_key = get_client_ip(request)
    now = time()
    with _LOGIN_ATTEMPTS_LOCK:
        locked_until = _LOGIN_LOCKED_UNTIL.get(client_key)
        if not locked_until:
            return 0
        if locked_until <= now:
            _LOGIN_LOCKED_UNTIL.pop(client_key, None)
            _LOGIN_ATTEMPTS.pop(client_key, None)
            return 0
        return max(1, int(locked_until - now))


def register_login_failure(
    request: Request,
    *,
    max_attempts: int,
    window_seconds: int,
    lockout_seconds: int,
) -> LoginFailureResult:
    client_key = get_client_ip(request)
    now = time()
    with _LOGIN_ATTEMPTS_LOCK:
        locked_until = _LOGIN_LOCKED_UNTIL.get(client_key)
        if locked_until and locked_until > now:
            return LoginFailureResult(
                attempts=max_attempts,
                locked=True,
                lock_seconds_remaining=max(1, int(locked_until - now)),
            )
        if locked_until and locked_until <= now:
            _LOGIN_LOCKED_UNTIL.pop(client_key, None)
            _LOGIN_ATTEMPTS.pop(client_key, None)

        attempts = [ts for ts in _LOGIN_ATTEMPTS.get(client_key, []) if now - ts <= window_seconds]
        attempts.append(now)
        _LOGIN_ATTEMPTS[client_key] = attempts

        if len(attempts) >= max_attempts:
            until = now + lockout_seconds
            _LOGIN_LOCKED_UNTIL[client_key] = until
            return LoginFailureResult(
                attempts=len(attempts),
                locked=True,
                lock_seconds_remaining=max(1, int(until - now)),
            )

        return LoginFailureResult(
            attempts=len(attempts),
            locked=False,
            lock_seconds_remaining=0,
        )


def clear_login_failures(request: Request) -> None:
    client_key = get_client_ip(request)
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.pop(client_key, None)
        _LOGIN_LOCKED_UNTIL.pop(client_key, None)


def reset_admin_auth_state_for_tests() -> None:
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.clear()
        _LOGIN_LOCKED_UNTIL.clear()


def validate_admin_security_config(settings: object) -> list[str]:
    errors: list[str] = []
    password = str(getattr(settings, "admin_password", "") or "").strip()
    min_len = int(getattr(settings, "admin_min_password_length", 10) or 10)
    base_path = normalize_admin_base_path(str(getattr(settings, "admin_base_path", "/admin")))
    allowlist = str(getattr(settings, "admin_ip_allowlist", "") or "").strip()
    jwt_secret = str(getattr(settings, "jwt_secret_key", "") or "")

    if not password:
        errors.append("TKD_ADMIN_PASSWORD is required when TKD_ADMIN_SECURITY_FAIL_FAST=true")
    elif len(password) < min_len:
        errors.append(
            f"TKD_ADMIN_PASSWORD must be at least {min_len} characters long "
            "(configurable with TKD_ADMIN_MIN_PASSWORD_LENGTH)"
        )

    if base_path == INTERNAL_ADMIN_BASE_PATH:
        errors.append("TKD_ADMIN_BASE_PATH must not be /admin in fail-fast mode")

    if not allowlist:
        errors.append("TKD_ADMIN_IP_ALLOWLIST is required in fail-fast mode")

    if jwt_secret == "change-me-in-production":
        errors.append("TKD_JWT_SECRET_KEY must not use the default value in fail-fast mode")

    return errors


def is_admin_request(request: Request) -> bool:
    """Same guard as the admin panel: the IP allowlist and, when TKD_ADMIN_PASSWORD is set, the login cookie."""
    return is_ip_allowed(request) and is_admin_authenticated(request)


def has_admin_login(request: Request) -> bool:
    """An administrator logged in to the panel from an allowed IP (requires TKD_ADMIN_PASSWORD).

    Used where a judge Bearer token is the default credential: without a configured admin password there is
    no administrator identity to present, so the token stays mandatory.
    """
    return is_admin_auth_enabled(request) and is_admin_request(request)
