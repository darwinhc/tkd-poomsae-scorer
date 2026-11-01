from pathlib import Path

import pytest

from tkd_scorer.infra.config.settings import get_settings


def test_get_settings_reads_env_from_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        (
            "TKD_HOST=0.0.0.0\n"
            "TKD_PORT=9090\n"
            "TKD_BASE_URL=http://127.0.0.1:9090\n"
            "TKD_JWT_SECRET_KEY=runtime-secret\n"
            "TKD_REQUIRE_POOMSAE_CATALOG_FILE=false\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TKD_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("TKD_JWT_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.port == 9090
        assert settings.jwt_secret_key == "runtime-secret"
    finally:
        get_settings.cache_clear()


def test_get_settings_fails_without_env_when_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TKD_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("TKD_REQUIRE_ENV_FILE", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Runtime .env file not found"):
            get_settings()
    finally:
        get_settings.cache_clear()
