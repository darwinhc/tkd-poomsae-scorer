from tkd_scorer.infra.config.runtime_base_url import replace_host_in_base_url, resolve_qr_base_url


def test_replace_host_in_base_url_keeps_port() -> None:
    result = replace_host_in_base_url("http://127.0.0.1:8080", "192.168.1.55")
    assert result == "http://192.168.1.55:8080"


def test_resolve_qr_base_url_uses_override_ip_when_enabled() -> None:
    result = resolve_qr_base_url(
        configured_base_url="http://127.0.0.1:8080",
        use_server_ip=True,
        server_ip_override="192.168.0.77",
    )
    assert result == "http://192.168.0.77:8080"


def test_resolve_qr_base_url_returns_configured_when_disabled() -> None:
    result = resolve_qr_base_url(
        configured_base_url="http://127.0.0.1:8080/",
        use_server_ip=False,
        server_ip_override="192.168.0.77",
    )
    assert result == "http://127.0.0.1:8080"


def _settings(**overrides):
    from tkd_scorer.infra.config.settings import Settings

    values = {
        "port": 8080,
        "public_base_url": "http://192.168.1.20:8080",
        "base_url": "http://127.0.0.1:8080",
        "qr_use_server_ip": True,
        "qr_server_ip_override": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_qr_base_url_uses_the_detected_server_ip_by_default(monkeypatch) -> None:
    from tkd_scorer.infra.config import runtime_base_url
    from tkd_scorer.infra.fastapi.dependencies import resolve_settings_qr_base_url

    monkeypatch.setattr(runtime_base_url, "detect_server_ipv4", lambda: "10.0.0.9")

    assert resolve_settings_qr_base_url(_settings()) == "http://10.0.0.9:8080"


def test_qr_base_url_override_wins_over_detection_and_over_the_public_url(monkeypatch) -> None:
    from tkd_scorer.infra.config import runtime_base_url
    from tkd_scorer.infra.fastapi.dependencies import resolve_settings_qr_base_url

    monkeypatch.setattr(runtime_base_url, "detect_server_ipv4", lambda: "10.0.0.9")

    assert resolve_settings_qr_base_url(_settings(qr_server_ip_override="192.168.50.5")) == "http://192.168.50.5:8080"
    assert (
        resolve_settings_qr_base_url(_settings(qr_use_server_ip=False, qr_server_ip_override=" 192.168.50.5 "))
        == "http://192.168.50.5:8080"
    )


def test_qr_base_url_without_server_ip_uses_the_configured_public_url(monkeypatch) -> None:
    from tkd_scorer.infra.config import runtime_base_url
    from tkd_scorer.infra.fastapi.dependencies import resolve_settings_qr_base_url

    monkeypatch.setattr(runtime_base_url, "detect_server_ipv4", lambda: "10.0.0.9")

    assert (
        resolve_settings_qr_base_url(_settings(qr_use_server_ip=False, public_base_url="https://scores.example.test/tkd/"))
        == "https://scores.example.test/tkd"
    )
    # Without TKD_PUBLIC_BASE_URL: TKD_BASE_URL as configured.
    assert (
        resolve_settings_qr_base_url(_settings(qr_use_server_ip=False, public_base_url=None, qr_server_ip_override=""))
        == "http://127.0.0.1:8080"
    )
