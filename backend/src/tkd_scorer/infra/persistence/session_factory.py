from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from tkd_scorer.infra.persistence.base import Base
from tkd_scorer.ports.security.credential_cipher_port import CredentialCipherPort

# Columns added after the first release. create_all() does not alter existing tables, so databases created
# by an older version get them through _add_missing_columns (idempotent, safe to run on every start).
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "stations": {
        "credential_encrypted": "TEXT",
    },
    "device_sessions": {
        "scorecard_session_id": "VARCHAR(100)",
    },
    "matches": {
        "judges_required": "INTEGER NOT NULL DEFAULT 1",
        "judge_session_ids": "TEXT NOT NULL DEFAULT '[]'",
        "removed_session_ids": "TEXT NOT NULL DEFAULT '[]'",
    },
    "score_events": {
        "score_target": "VARCHAR(40)",
    },
    "finalization_records": {
        "round_numbers": "TEXT NOT NULL DEFAULT '[]'",
        "response_payload": "TEXT NOT NULL DEFAULT '{}'",
    },
}


def create_engine_and_session_factory(database_url: str) -> tuple:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, echo=False, connect_args=connect_args)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    return engine, session_factory


def create_schema(engine, *, credential_cipher: CredentialCipherPort | None = None) -> None:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns(engine)
    if credential_cipher is not None:
        _encrypt_plain_station_credentials(engine, credential_cipher)


def _add_missing_columns(engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def _encrypt_plain_station_credentials(engine, credential_cipher: CredentialCipherPort) -> None:
    """Older versions stored the station PIN in plain text (stations.credential_plain).

    Encrypts every plain value into credential_encrypted and clears the plain column. Idempotent: once the
    plain values are cleared there is nothing left to migrate (databases created by this version do not
    have the column at all).
    """
    inspector = inspect(engine)
    if not inspector.has_table("stations"):
        return
    columns = {column["name"] for column in inspector.get_columns("stations")}
    if "credential_plain" not in columns:
        return
    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, credential_plain FROM stations WHERE credential_plain IS NOT NULL")
        ).all()
        for station_id, plain in rows:
            encrypted = credential_cipher.encrypt(plain) if plain else None
            connection.execute(
                text(
                    "UPDATE stations SET credential_encrypted = :encrypted, credential_plain = NULL "
                    "WHERE id = :station_id"
                ),
                {"encrypted": encrypted, "station_id": station_id},
            )
