from pathlib import Path

INFRA = Path(__file__).resolve().parents[2] / "src" / "tkd_scorer" / "infra"


def test_templates_do_not_load_assets_from_the_internet() -> None:
    # The system runs on a LAN without internet: every asset must be served locally.
    offenders = [
        f"{path.name}: {line.strip()}"
        for path in (INFRA / "templates").rglob("*.html")
        for line in path.read_text(encoding="utf-8").splitlines()
        if ("src=\"http" in line or "href=\"http" in line)
    ]
    assert offenders == []


def test_local_assets_referenced_by_base_template_exist() -> None:
    for relative in (
        "static/admin/tailwind.css",
        "static/admin/admin.css",
        "static/vendor/lucide.min.js",
        "static/fonts/nunito-sans-latin-400-normal.woff2",
    ):
        assert (INFRA / relative).is_file(), relative
