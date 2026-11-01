import json
import string

import pytest

from tkd_scorer.entry_points.fastapi.admin_views.labels import status_label
from tkd_scorer.infra.i18n import (
    LOCALES_DIR,
    SUPPORTED_LANGUAGES,
    load_catalog,
    normalize_language,
    translate,
)


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def _raw_catalog(language: str) -> dict[str, str]:
    with (LOCALES_DIR / f"{language}.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_all_locales_have_the_same_keys() -> None:
    english_keys = set(_raw_catalog("en"))
    assert english_keys
    for language in SUPPORTED_LANGUAGES:
        assert set(_raw_catalog(language)) == english_keys, language


def test_all_locales_use_the_same_placeholders() -> None:
    english = _raw_catalog("en")
    for language in SUPPORTED_LANGUAGES:
        catalog = _raw_catalog(language)
        for key, text in english.items():
            assert _placeholders(catalog[key]) == _placeholders(text), (language, key)


def test_all_locale_values_are_non_empty_strings() -> None:
    for language in SUPPORTED_LANGUAGES:
        for key, text in _raw_catalog(language).items():
            assert isinstance(text, str) and text.strip(), (language, key)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("en", "en"), ("ES", "es"), ("es-CO", "es"), ("fr", "en"), (None, "en"), ("", "en")],
)
def test_normalize_language(raw: str | None, expected: str) -> None:
    assert normalize_language(raw) == expected


def test_translate_formats_placeholders_and_falls_back_to_key() -> None:
    assert translate("scoreboard.connected_judges", "en", count=3) == "Connected judges: 3"
    assert translate("scoreboard.connected_judges", "es", count=3) == load_catalog("es")[
        "scoreboard.connected_judges"
    ].format(count=3)
    assert translate("missing.key", "es") == "missing.key"


def test_status_label_is_language_aware() -> None:
    assert status_label("in_progress", "en") == "In progress"
    assert status_label("in_progress", "es") == load_catalog("es")["status.in_progress"]
    assert status_label("some_unknown_status", "en") == "Some unknown status"
    assert status_label(None, "en") == "-"
