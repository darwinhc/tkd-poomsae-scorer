from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from random import Random, SystemRandom

from tkd_scorer.domain.exceptions.errors import ValidationError

try:
    import yaml
except ImportError:  # pragma: no cover - guarded fallback
    yaml = None

_LOGGER = logging.getLogger("tkd_scorer.domain.poomsae_draw")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
POOMSAE_CATALOG_ENV = "TKD_POOMSAE_CATALOG_PATH"
POOMSAE_CATALOG_PATH = Path("config") / "poomsae_categories.yaml"

DEFAULT_POOMSAES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "beginners": ("Taeguk 1", "Taeguk 2", "Taeguk 3", "Taeguk 4"),
    "advanced": ("Taeguk 5", "Taeguk 6", "Taeguk 7", "Taeguk 8"),
    "black_belts": ("Koryo", "Keumgang", "Taebaek", "Pyongwon", "Sipjin", "Jitae"),
}

DEFAULT_CATEGORY_LABELS: dict[str, str] = {
    "beginners": "Beginners",
    "advanced": "Advanced",
    "black_belts": "Black belts",
}


def list_supported_categories() -> tuple[str, ...]:
    poomsaes, _ = _catalog()
    return tuple(poomsaes.keys())


def category_label(category_id: str) -> str:
    normalized = category_id.strip().lower()
    _, labels = _catalog()
    if normalized not in labels:
        raise ValidationError("Invalid match category")
    return labels[normalized]


def poomsaes_for_category(category_id: str) -> tuple[str, ...]:
    normalized = category_id.strip().lower()
    poomsaes_by_category, _ = _catalog()
    poomsaes = poomsaes_by_category.get(normalized)
    if poomsaes is None:
        raise ValidationError("Invalid match category")
    return poomsaes


def validate_selected_poomsaes(category_id: str, selected_poomsaes: list[str]) -> list[str]:
    allowed_for_category = set(poomsaes_for_category(category_id))
    poomsaes_by_category, _ = _catalog()
    allowed_global = {item for poomsaes in poomsaes_by_category.values() for item in poomsaes}
    cleaned: list[str] = []
    for poomsae in selected_poomsaes:
        candidate = poomsae.strip()
        if not candidate:
            continue
        if candidate not in allowed_global:
            raise ValidationError(f"Poomsae not available: {candidate}")
        if candidate not in cleaned:
            cleaned.append(candidate)

    if not cleaned:
        raise ValidationError("At least one poomsae must be selected")
    if not any(item in allowed_for_category for item in cleaned):
        raise ValidationError("At least one poomsae from the selected category must be included")
    return cleaned


def draw_poomsaes_for_match(
    *,
    category_id: str,
    selected_poomsaes: list[str],
    total_rounds: int,
    rng: Random | None = None,
) -> list[str]:
    if total_rounds <= 0:
        raise ValidationError("totalRounds must be greater than zero")

    cleaned = validate_selected_poomsaes(category_id, selected_poomsaes)
    if len(cleaned) < total_rounds:
        raise ValidationError("Not enough poomsaes selected to draw all rounds")

    random_source = rng or SystemRandom()
    return list(random_source.sample(cleaned, k=total_rounds))


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    return _load_catalog()


def _load_catalog() -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    catalog_path = _resolve_catalog_path()
    if not catalog_path.exists():
        return DEFAULT_POOMSAES_BY_CATEGORY, DEFAULT_CATEGORY_LABELS
    if yaml is None:
        _LOGGER.warning(
            "poomsae_catalog_yaml_ignored path=%s reason=pyyaml_not_installed",
            catalog_path,
        )
        return DEFAULT_POOMSAES_BY_CATEGORY, DEFAULT_CATEGORY_LABELS

    try:
        with catalog_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except Exception as exc:  # pragma: no cover - defensive logging
        _LOGGER.warning(
            "poomsae_catalog_yaml_invalid path=%s error=%s",
            catalog_path,
            str(exc),
        )
        return DEFAULT_POOMSAES_BY_CATEGORY, DEFAULT_CATEGORY_LABELS

    parsed = _parse_catalog(raw)
    if parsed is None:
        _LOGGER.warning(
            "poomsae_catalog_yaml_invalid_structure path=%s",
            catalog_path,
        )
        return DEFAULT_POOMSAES_BY_CATEGORY, DEFAULT_CATEGORY_LABELS
    return parsed


def validate_external_catalog_or_raise(catalog_path: Path) -> None:
    if not catalog_path.exists():
        raise RuntimeError(
            "Poomsae category catalog file not found. "
            f"Expected path: {catalog_path}"
        )
    if yaml is None:
        raise RuntimeError("Cannot validate YAML because PyYAML is not installed")
    try:
        with catalog_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except Exception as exc:
        raise RuntimeError(
            "Poomsae category catalog YAML file is invalid: "
            f"{catalog_path} | details: {exc}"
        ) from exc
    if _parse_catalog(raw) is None:
        raise RuntimeError(
            "Poomsae category catalog YAML file does not match the expected structure: "
            f"{catalog_path}"
        )


def _resolve_catalog_path() -> Path:
    override = os.getenv(POOMSAE_CATALOG_ENV, "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (_runtime_root() / candidate).resolve()
    if POOMSAE_CATALOG_PATH.is_absolute():
        return POOMSAE_CATALOG_PATH.resolve()
    return (_runtime_root() / POOMSAE_CATALOG_PATH).resolve()


def _runtime_root() -> Path:
    override = os.getenv("TKD_RUNTIME_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _parse_catalog(raw: object) -> tuple[dict[str, tuple[str, ...]], dict[str, str]] | None:
    if not isinstance(raw, dict):
        return None

    categories_node = raw.get("categories")
    if isinstance(categories_node, dict):
        source = categories_node
    elif categories_node is None:
        source = raw
    else:
        return None

    poomsaes_by_category: dict[str, tuple[str, ...]] = {}
    labels_by_category: dict[str, str] = {}

    for category_id, value in source.items():
        if not isinstance(category_id, str) or not category_id.strip():
            return None
        if not isinstance(value, dict):
            return None

        normalized_id = category_id.strip().lower()
        label = value.get("label")
        poomsaes = value.get("poomsaes")

        if not isinstance(label, str) or not label.strip():
            return None
        if not isinstance(poomsaes, list):
            return None

        cleaned: list[str] = []
        for poomsae in poomsaes:
            if not isinstance(poomsae, str) or not poomsae.strip():
                return None
            candidate = poomsae.strip()
            if candidate not in cleaned:
                cleaned.append(candidate)

        if not cleaned:
            return None

        poomsaes_by_category[normalized_id] = tuple(cleaned)
        labels_by_category[normalized_id] = label.strip()

    if not poomsaes_by_category:
        return None

    return poomsaes_by_category, labels_by_category
