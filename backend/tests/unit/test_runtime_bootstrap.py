from pathlib import Path

import pytest

from tkd_scorer.infra.config.runtime_bootstrap import prepare_runtime
from tkd_scorer.infra.config.settings import Settings


def _write_catalog(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "categories:\n"
            "  beginners:\n"
            "    label: Beginners\n"
            "    poomsaes:\n"
            "      - Taeguk 1\n"
        ),
        encoding="utf-8",
    )


def test_prepare_runtime_creates_dirs_and_resolves_sqlite_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TKD_RUNTIME_ROOT", str(tmp_path))
    catalog_path = tmp_path / "config" / "poomsae_categories.yaml"
    _write_catalog(catalog_path)

    settings = Settings(
        database_url="sqlite:///./data/local.db",
        data_dir="data",
        logs_dir="logs",
        poomsae_catalog_path="config/poomsae_categories.yaml",
        require_poomsae_catalog_file=True,
    )

    runtime = prepare_runtime(settings)

    assert runtime.data_dir == tmp_path / "data"
    assert runtime.logs_dir == tmp_path / "logs"
    assert runtime.log_file_path == tmp_path / "logs" / settings.log_file_name
    assert runtime.poomsae_catalog_path == catalog_path
    assert runtime.database_url.startswith("sqlite:////")
    assert str(tmp_path / "data" / "local.db") in runtime.database_url


def test_prepare_runtime_fails_when_catalog_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TKD_RUNTIME_ROOT", str(tmp_path))
    settings = Settings(
        poomsae_catalog_path="config/poomsae_categories.yaml",
        require_poomsae_catalog_file=True,
    )

    with pytest.raises(RuntimeError, match="Poomsae category catalog file not found"):
        prepare_runtime(settings)

