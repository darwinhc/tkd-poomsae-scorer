from random import Random

import pytest

import tkd_scorer.domain.services.poomsae_draw as poomsae_draw
from tkd_scorer.domain.exceptions.errors import ValidationError
from tkd_scorer.domain.services.poomsae_draw import (
    category_label,
    draw_poomsaes_for_match,
    list_supported_categories,
    validate_selected_poomsaes,
)


def test_list_supported_categories_includes_expected_levels() -> None:
    assert list_supported_categories() == ("beginners", "advanced", "black_belts")


def test_validate_selected_poomsaes_rejects_unknown_poomsae() -> None:
    with pytest.raises(ValidationError):
        validate_selected_poomsaes("beginners", ["Unknown Poomsae"])


def test_validate_selected_poomsaes_allows_mixed_categories_if_base_category_present() -> None:
    selected = validate_selected_poomsaes("beginners", ["Taeguk 1", "Koryo"])
    assert selected == ["Taeguk 1", "Koryo"]


def test_draw_poomsaes_for_match_is_deterministic_when_rng_is_injected() -> None:
    drawn = draw_poomsaes_for_match(
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7", "Taeguk 8"],
        total_rounds=2,
        rng=Random(11),
    )
    assert drawn == ["Taeguk 8", "Taeguk 7"]


def test_draw_poomsaes_requires_enough_selection_for_rounds() -> None:
    with pytest.raises(ValidationError):
        draw_poomsaes_for_match(
            category_id="black_belts",
            selected_poomsaes=["Koryo"],
            total_rounds=2,
            rng=Random(3),
        )


def test_category_label_uses_spanish_labels() -> None:
    assert category_label("black_belts") == "Black belts"


def test_catalog_uses_yaml_override_when_file_exists(tmp_path, monkeypatch) -> None:
    yaml_path = tmp_path / "poomsae_categories.yaml"
    yaml_path.write_text(
        (
            "categories:\n"
            "  infantil:\n"
            "    label: Infantil\n"
            "    poomsaes:\n"
            "      - Taeguk 1\n"
            "      - Taeguk 2\n"
            "  elite:\n"
            "    label: Elite\n"
            "    poomsaes:\n"
            "      - Koryo\n"
            "      - Keumgang\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(poomsae_draw, "POOMSAE_CATALOG_PATH", yaml_path)
    poomsae_draw._catalog.cache_clear()
    try:
        assert list_supported_categories() == ("infantil", "elite")
        assert category_label("infantil") == "Infantil"
        assert validate_selected_poomsaes("infantil", ["Taeguk 2", "Koryo"]) == ["Taeguk 2", "Koryo"]
    finally:
        poomsae_draw._catalog.cache_clear()
