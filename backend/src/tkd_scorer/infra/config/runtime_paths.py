from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            root = Path(meipass)
            package_candidate = root / "tkd_scorer"
            if package_candidate.exists():
                return package_candidate
            return root
    return Path(__file__).resolve().parents[2]


def project_root_dev() -> Path:
    return Path(__file__).resolve().parents[4]


def runtime_root() -> Path:
    override = os.getenv("TKD_RUNTIME_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        parent_dir = exe_dir.parent
        if (exe_dir / ".env").exists() or (exe_dir / "config").exists():
            return exe_dir
        if (parent_dir / ".env").exists() or (parent_dir / "config").exists():
            return parent_dir
        return exe_dir
    return project_root_dev()


def env_file_path() -> Path:
    return runtime_root() / ".env"


def resolve_runtime_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (runtime_root() / candidate).resolve()
