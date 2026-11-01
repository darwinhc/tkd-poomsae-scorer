"""Station PIN stored encrypted (Fernet, key derived from TKD_JWT_SECRET_KEY) instead of plain text."""

from pathlib import Path

from sqlalchemy import create_engine, text

from tests.unit.fakes import FixedClock, ReversibleCredentialCipher
from tests.unit.test_admin_station_live_snapshot import _BootstrapStub, _CredentialGeneratorStub
from tkd_scorer.adapters.security.credential_cipher import FernetCredentialCipher
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases
from tkd_scorer.infra.persistence.session_factory import create_schema


def _admin(fixture_bundle, cipher) -> AdminViewUseCases:
    return AdminViewUseCases(
        station_repository=fixture_bundle["stations"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        bootstrap_service=_BootstrapStub(),
        credential_service=fixture_bundle["credential_service"],
        credential_generator=_CredentialGeneratorStub(),
        clock=FixedClock(),
        id_generator=fixture_bundle["ids"],
        base_url="http://127.0.0.1:8080",
        environment="test",
        tournament_id="tkd-test",
        protocol_version="v1",
        bootstrap_ttl_seconds=180,
        station_credential_ttl_seconds=3600,
        station_credential_rotation_seconds=20,
        history_retention_matches=10,
        credential_cipher=cipher,
    )


def test_fernet_cipher_round_trips_and_fails_gracefully_with_another_key() -> None:
    cipher = FernetCredentialCipher(secret_key="server-secret")
    encrypted = cipher.encrypt("4821")

    assert "4821" not in encrypted
    assert cipher.decrypt(encrypted) == "4821"
    assert FernetCredentialCipher(secret_key="server-secret").decrypt(encrypted) == "4821"
    assert FernetCredentialCipher(secret_key="rotated-secret").decrypt(encrypted) is None
    assert cipher.decrypt("not-a-fernet-token") is None


def test_created_and_rotated_credentials_are_stored_encrypted_and_revealable(fixture_bundle) -> None:
    admin = _admin(fixture_bundle, ReversibleCredentialCipher())

    admin.create_station(station_name="Station 02", station_id=None, expected_judge_name=None, credential="4821", actor="t")
    station = fixture_bundle["stations"].get_by_id("station-02")
    assert station.credential_encrypted == "enc[test-key]:1284"
    assert admin.get_station_credential("station-02", reveal=True).revealed == "4821"
    assert admin.get_station_credential("station-02", reveal=False).masked == "4**1"

    rotated = admin.rotate_station_credential("station-02", actor="t")
    assert rotated.revealed == "999999"
    assert fixture_bundle["stations"].get_by_id("station-02").credential_encrypted == "enc[test-key]:999999"


def test_credential_written_with_another_server_key_asks_to_rotate(fixture_bundle) -> None:
    station = fixture_bundle["stations"].get_by_id("station-01")
    station.credential_encrypted = ReversibleCredentialCipher(key="old-key").encrypt("1234")
    fixture_bundle["stations"].save(station)
    admin = _admin(fixture_bundle, ReversibleCredentialCipher(key="new-key"))

    view = admin.get_station_credential("station-01", reveal=True)
    snapshot = admin.station_live_snapshot(
        station_id="station-01", rotate_credential=False, actor="t", reveal_credential=True
    )

    assert view.unreadable is True
    assert view.revealed is None
    assert snapshot.credential_unreadable is True


def test_startup_migration_encrypts_plain_pins_and_clears_the_plain_column(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        # Shape of the stations table written by older versions (plain PIN copy).
        connection.execute(
            text(
                "CREATE TABLE stations (id VARCHAR(64) PRIMARY KEY, name VARCHAR(120) NOT NULL, "
                "status VARCHAR(32) NOT NULL, credential_hash VARCHAR(255) NOT NULL, "
                "credential_plain VARCHAR(64), credential_expires_at DATETIME, expected_judge_name VARCHAR(120), "
                "active_session_id VARCHAR(100), updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stations (id, name, status, credential_hash, credential_plain) "
                "VALUES ('station-01', 'Station 01', 'active', 'hash', '4821'), "
                "('station-02', 'Station 02', 'active', 'hash', NULL)"
            )
        )
    cipher = FernetCredentialCipher(secret_key="server-secret")

    create_schema(engine, credential_cipher=cipher)
    create_schema(engine, credential_cipher=cipher)  # idempotent

    with engine.begin() as connection:
        rows = dict(
            connection.execute(text("SELECT id, credential_encrypted FROM stations")).all()
        )
        plain = connection.execute(text("SELECT credential_plain FROM stations WHERE credential_plain IS NOT NULL")).all()
    assert plain == []
    assert cipher.decrypt(rows["station-01"]) == "4821"
    assert rows["station-02"] is None
    engine.dispose()
