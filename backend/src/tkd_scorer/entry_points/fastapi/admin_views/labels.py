from __future__ import annotations

from collections.abc import Callable

from tkd_scorer.infra.i18n import DEFAULT_LANGUAGE, load_catalog, normalize_language, translate

_STATUS_KEY_PREFIX = "status."


def status_label(value: str | None, language: str = DEFAULT_LANGUAGE) -> str:
    if value is None:
        return "-"
    normalized = value.strip().lower()
    if not normalized:
        return "-"
    key = f"{_STATUS_KEY_PREFIX}{normalized}"
    if key in load_catalog(normalize_language(language)) or key in load_catalog(DEFAULT_LANGUAGE):
        return translate(key, language)
    return normalized.replace("_", " ").capitalize()


def make_status_label_filter(language: str) -> Callable[[str | None], str]:
    resolved = normalize_language(language)

    def _filter(value: str | None) -> str:
        return status_label(value, resolved)

    return _filter
