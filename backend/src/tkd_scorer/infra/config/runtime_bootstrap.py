from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine.url import make_url

from tkd_scorer.domain.services.poomsae_draw import validate_external_catalog_or_raise
from tkd_scorer.infra.config.runtime_paths import resolve_runtime_path, runtime_root
from tkd_scorer.infra.config.settings import Settings


@dataclass(frozen=True)
class RuntimeBootstrap:
    runtime_root: Path
    data_dir: Path
    logs_dir: Path
    poomsae_catalog_path: Path
    log_file_path: Path
    database_url: str


def prepare_runtime(settings: Settings) -> RuntimeBootstrap:
    root = runtime_root()
    data_dir = resolve_runtime_path(settings.data_dir)
    logs_dir = resolve_runtime_path(settings.logs_dir)
    poomsae_catalog_path = resolve_runtime_path(settings.poomsae_catalog_path)

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    poomsae_catalog_path.parent.mkdir(parents=True, exist_ok=True)

    if settings.require_poomsae_catalog_file:
        validate_external_catalog_or_raise(poomsae_catalog_path)

    resolved_db_url = _resolve_database_url(settings.database_url, root)
    log_file_path = logs_dir / settings.log_file_name
    return RuntimeBootstrap(
        runtime_root=root,
        data_dir=data_dir,
        logs_dir=logs_dir,
        poomsae_catalog_path=poomsae_catalog_path,
        log_file_path=log_file_path,
        database_url=resolved_db_url,
    )


def _resolve_database_url(database_url: str, root: Path) -> str:
    url = make_url(database_url)
    if url.drivername != "sqlite":
        return database_url

    db_name = url.database
    if db_name is None or db_name == ":memory:":
        return database_url

    db_path = Path(db_name)
    if not db_path.is_absolute():
        db_path = (root / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(url.set(database=str(db_path)))

