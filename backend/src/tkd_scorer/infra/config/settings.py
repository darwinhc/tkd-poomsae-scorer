import os
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tkd_scorer.infra.config.runtime_paths import env_file_path
from tkd_scorer.infra.i18n import SUPPORTED_LANGUAGES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TKD_",
        extra="ignore",
    )

    app_name: str = "tkd-poomsae-scorer"
    environment: str = "local"
    host: str = "0.0.0.0"
    port: int = 8080
    public_base_url: str | None = None
    base_url: str = "http://127.0.0.1:8080"
    qr_use_server_ip: bool = True
    qr_server_ip_override: str | None = None
    protocol_version: str = "v1"
    tournament_id: str = "tkd-poomsae-local"

    database_url: str = "sqlite:///./data/tkd_scorer.db"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    require_env_file: bool = True
    require_poomsae_catalog_file: bool = True
    poomsae_catalog_path: str = "config/poomsae_categories.yaml"
    data_dir: str = "data"
    logs_dir: str = "logs"
    log_file_name: str = "tkd_server.log"
    log_level: str = "INFO"
    ui_language: str = "en"

    bootstrap_token_ttl_seconds: int = 180
    operational_token_ttl_seconds: int = 60 * 60 * 24 * 30
    station_credential_ttl_seconds: int = 60 * 60 * 8
    station_credential_rotation_seconds: int = 20
    admin_base_path: str = "/admin"
    admin_password: str = ""
    admin_auth_cookie_name: str = "tkd_admin_auth"
    admin_auth_cookie_ttl_seconds: int = 60 * 60 * 24
    admin_cookie_secure: bool = False
    admin_ip_allowlist: str = ""
    admin_trust_proxy_headers: bool = False
    admin_login_max_attempts: int = 5
    admin_login_window_seconds: int = 60 * 5
    admin_login_lockout_seconds: int = 60 * 5
    admin_min_password_length: int = 10
    admin_security_fail_fast: bool = True
    admin_live_refresh_seconds: int = 20
    admin_live_winner_overlay_seconds: int = 12
    live_min_width_px: int = 768
    history_retention_matches: int = 100
    history_delete_bulk_scan_limit: int = 100000
    match_query_limit_active_lookup: int = 50
    match_query_limit_scoreboard: int = 300

    websocket_ping_interval_seconds: int = 20
    websocket_stale_timeout_seconds: int = 60
    judge_default_rounds: int = 2
    judge_default_starting_score: float = 4.0
    judge_presentation_category_start_score: float = 2.0
    judge_action_value_1: float = 0.1
    judge_action_value_2: float = 0.3
    judge_official_counts: str = "3,5,7"
    station_credential_create_length: int = 4
    station_credential_rotate_length: int = 6
    create_match_default_starting_score: float = 4.0

    @field_validator("admin_base_path")
    @classmethod
    def _validate_admin_base_path(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return "/admin"
        if not raw.startswith("/"):
            raw = f"/{raw}"
        normalized = raw.rstrip("/")
        if not normalized or normalized == "/":
            return "/admin"
        return normalized

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("TKD_HOST must not be empty")
        return cleaned

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("TKD_PORT must be between 1 and 65535")
        return value

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        cleaned = (value or "").strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TKD_BASE_URL must be a valid http(s) URL")
        return cleaned

    @field_validator("public_base_url")
    @classmethod
    def _validate_public_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TKD_PUBLIC_BASE_URL must be a valid http(s) URL")
        return cleaned

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        cleaned = (value or "INFO").strip().upper()
        valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if cleaned not in valid:
            raise ValueError(f"TKD_LOG_LEVEL must be one of: {', '.join(sorted(valid))}")
        return cleaned

    @field_validator("ui_language")
    @classmethod
    def _validate_ui_language(cls, value: str) -> str:
        cleaned = (value or "en").strip().lower()
        if cleaned not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"TKD_UI_LANGUAGE must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return cleaned

    @field_validator("admin_live_winner_overlay_seconds")
    @classmethod
    def _validate_live_winner_overlay_seconds(cls, value: int) -> int:
        if value < 1:
            raise ValueError("TKD_ADMIN_LIVE_WINNER_OVERLAY_SECONDS must be >= 1")
        return value

    @field_validator(
        "live_min_width_px",
        "history_retention_matches",
        "history_delete_bulk_scan_limit",
        "match_query_limit_active_lookup",
        "match_query_limit_scoreboard",
        "websocket_ping_interval_seconds",
        "websocket_stale_timeout_seconds",
        "station_credential_create_length",
        "station_credential_rotate_length",
    )
    @classmethod
    def _validate_positive_ints(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be >= 1")
        return value

    @field_validator("judge_official_counts")
    @classmethod
    def _validate_judge_official_counts(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("TKD_JUDGE_OFFICIAL_COUNTS must not be empty")
        parsed = []
        for item in cleaned.split(","):
            candidate = item.strip()
            if not candidate:
                continue
            try:
                count = int(candidate)
            except ValueError as exc:
                raise ValueError("TKD_JUDGE_OFFICIAL_COUNTS must contain comma-separated integers") from exc
            if count <= 0:
                raise ValueError("TKD_JUDGE_OFFICIAL_COUNTS must contain positive integers")
            parsed.append(str(count))
        if not parsed:
            raise ValueError("TKD_JUDGE_OFFICIAL_COUNTS must not end up empty")
        return ",".join(parsed)

    @property
    def effective_public_base_url(self) -> str:
        return self.public_base_url or self.base_url

    @property
    def judge_official_counts_values(self) -> set[int]:
        return {int(item.strip()) for item in self.judge_official_counts.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_path = env_file_path()
    require_env_file_raw = os.getenv("TKD_REQUIRE_ENV_FILE", "true").strip().lower()
    require_env_file = require_env_file_raw not in {"0", "false", "no"}
    if require_env_file and not env_path.exists():
        raise RuntimeError(
            "Runtime .env file not found. "
            f"Expected path: {env_path}"
        )
    if env_path.exists():
        return Settings(_env_file=str(env_path), _env_file_encoding="utf-8")
    return Settings()
