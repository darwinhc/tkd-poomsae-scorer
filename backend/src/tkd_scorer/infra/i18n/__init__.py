"""Minimal translation catalog for the admin panel and the TV scoreboard.

Catalogs live in ``locales/<lang>.json`` as flat ``{key: text}`` maps. Texts may
contain ``{name}`` placeholders that are filled with keyword arguments.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es")
DEFAULT_LANGUAGE = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_LOGGER = logging.getLogger("tkd_scorer.infra.i18n")


def normalize_language(value: str | None) -> str:
    candidate = (value or "").strip().lower().replace("_", "-").split("-")[0]
    if candidate in SUPPORTED_LANGUAGES:
        return candidate
    return DEFAULT_LANGUAGE


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def load_catalog(language: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{normalize_language(language)}.json"
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid translation catalog: {path}")
    return {str(key): str(value) for key, value in raw.items()}


def translate(key: str, language: str = DEFAULT_LANGUAGE, **params: object) -> str:
    catalog = load_catalog(normalize_language(language))
    text = catalog.get(key)
    if text is None:
        text = load_catalog(DEFAULT_LANGUAGE).get(key)
    if text is None:
        _LOGGER.warning("i18n_missing_key key=%s language=%s", key, language)
        return key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            _LOGGER.warning("i18n_format_failed key=%s language=%s", key, language)
            return text
    return text


def make_translator(language: str) -> Callable[..., str]:
    resolved = normalize_language(language)

    def _t(key: str, **params: object) -> str:
        return translate(key, resolved, **params)

    return _t
