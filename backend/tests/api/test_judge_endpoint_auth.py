"""Authentication of the judge endpoints, WebSocket bind / keep-alive, session replacement and closed matches."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tkd_scorer.infra.config.settings import get_settings

ADMIN_PASSWORD = "endpoint-auth-admin"


def _client(tmp_path: Path) -> TestClient:
    os.environ["TKD_DATABASE_URL"] = f"sqlite:///{tmp_path / 'endpoint_auth.db'}"
    os.environ["TKD_JWT_SECRET_KEY"] = "test-jwt-secret"
    os.environ["TKD_ADMIN_PASSWORD"] = ADMIN_PASSWORD
    os.environ["TKD_ADMIN_BASE_PATH"] = "/admin"
    os.environ["TKD_ADMIN_IP_ALLOWLIST"] = ""
    os.environ["TKD_ADMIN_SECURITY_FAIL_FAST"] = "false"
    os.environ["TKD_ADMIN_TRUST_PROXY_HEADERS"] = "false"
    os.environ["TKD_UI_LANGUAGE"] = "en"
    get_settings.cache_clear()
    from tkd_scorer.infra.fastapi.admin_auth import reset_admin_auth_state_for_tests

    reset_admin_auth_state_for_tests()
    from tkd_scorer.entry_points.fastapi.app import create_app

    return TestClient(create_app())


def _login(client: TestClient) -> None:
    login = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "next": "/admin"}, follow_redirects=False)
    assert login.status_code == 303


def _logout(client: TestClient) -> None:
    client.cookies.clear()


def _station(client: TestClient, station_id: str = "station-01") -> None:
    created = client.post(
        "/admin/stations/create",
        data={"station_name": station_id, "station_id": station_id, "credential": "1234", "actor": "test"},
        follow_redirects=False,
    )
    assert created.status_code == 303


def _connect(client: TestClient, judge: str, device: str, station_id: str = "station-01", **extra) -> dict:
    response = client.post(
        "/stations/connect",
        json={"stationId": station_id, "judgeName": judge, "credential": "1234", "deviceId": device, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _bearer(judge: dict) -> dict:
    return {"Authorization": f"Bearer {judge['accessToken']}"}


def _create_match(client: TestClient, judge: dict, station_id: str = "station-01"):
    return client.post(
        "/matches",
        json={
            "stationId": station_id,
            "sessionId": judge["sessionId"],
            "judgeName": "Judge 1",
            "competitorLeftName": "Red",
            "competitorRightName": "Blue",
            "totalRounds": 2,
        },
        headers=_bearer(judge),
    )


def _score_event(match_id: str, judge: dict, judge_name: str, sequence: int) -> dict:
    return {
        "eventId": f"{judge['sessionId']}-{sequence}",
        "idempotencyKey": f"{judge['sessionId']}-{sequence}",
        "sessionId": judge["sessionId"],
        "stationId": "station-01",
        "matchId": match_id,
        "roundNumber": 1,
        "athleteSide": "RED",
        "scoreTarget": "TECHNIQUE",
        "scoreDelta": -0.1,
        "occurredAt": "2026-03-18T12:00:00Z",
        "sequence": sequence,
        "judgeName": judge_name,
    }


def test_judge_endpoints_require_the_bearer_token_of_the_same_station(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _station(client, "station-02")
        _logout(client)
        judge = _connect(client, "Judge 1", "device-1")
        other = _connect(client, "Judge 9", "device-9", station_id="station-02")

        body = {
            "stationId": "station-01",
            "sessionId": judge["sessionId"],
            "judgeName": "Judge 1",
            "competitorLeftName": "Red",
            "competitorRightName": "Blue",
        }
        assert client.post("/matches", json=body).status_code == 401
        assert client.post("/matches", json=body, headers=_bearer(other)).status_code == 401
        created = _create_match(client, judge)
        assert created.status_code == 200
        match_id = created.json()["id"]

        for method, path in (
            ("post", f"/matches/{match_id}/next-round"),
            ("post", f"/matches/{match_id}/reset-round"),
            ("post", f"/matches/{match_id}/reset-match"),
            ("get", f"/matches/{match_id}/summary"),
            ("get", "/stations/station-01/active-session"),
        ):
            kwargs = {"json": {"actor": "x"}} if method == "post" else {}
            assert getattr(client, method)(path, **kwargs).status_code == 401, path

        # A token of another station cannot read or drive this station's match.
        assert client.get(f"/matches/{match_id}/summary", headers=_bearer(other)).status_code == 401
        assert client.get("/stations/station-01/active-session", headers=_bearer(other)).status_code == 401
        assert (
            client.post(f"/matches/{match_id}/next-round", json={"actor": "x"}, headers=_bearer(other)).status_code
            == 401
        )

        assert client.get(f"/matches/{match_id}/summary", headers=_bearer(judge)).status_code == 200
        assert client.get("/stations/station-01/active-session", headers=_bearer(judge)).status_code == 200
        assert (
            client.post(f"/matches/{match_id}/next-round", json={"actor": "x"}, headers=_bearer(judge)).status_code
            == 200
        )


def test_resets_of_the_shared_match_are_for_the_administrator_only(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _logout(client)
        judge = _connect(client, "Judge 1", "device-1")
        match_id = _create_match(client, judge).json()["id"]

        for action in ("reset-round", "reset-match"):
            rejected = client.post(f"/matches/{match_id}/{action}", json={"actor": "x"}, headers=_bearer(judge))
            assert rejected.status_code == 403, action

        _login(client)
        for action in ("reset-round", "reset-match"):
            accepted = client.post(f"/matches/{match_id}/{action}", json={"actor": "admin"})
            assert accepted.status_code == 200, action
        # The administrator can also read the summary without a judge token.
        assert client.get(f"/matches/{match_id}/summary").status_code == 200


def test_bootstrap_endpoints_need_the_admin_login_and_public_endpoints_stay_open(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        payload = {"stationId": "station-01", "stationName": "Station 01", "tournamentId": "tkd"}
        assert client.post("/bootstrap/generate", json=payload).status_code == 403
        assert client.post("/bootstrap/validate", json={"bootstrapToken": "x"}).status_code == 403

        _login(client)
        generated = client.post("/bootstrap/generate", json=payload)
        assert generated.status_code == 200
        token = generated.json()["bootstrapToken"]
        assert client.post("/bootstrap/validate", json={"bootstrapToken": token}).status_code == 200
        _station(client)
        _logout(client)

        assert client.get("/health").status_code == 200
        assert client.get("/stations/active").status_code == 200
        assert client.get("/scoreboard/station-01").status_code == 200
        _connect(client, "Judge 1", "device-1")


def test_websocket_bind_always_validates_the_token(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _logout(client)
        judge = _connect(client, "Judge 1", "device-1")
        other = _connect(client, "Judge 2", "device-2")

        for bind in (
            {"type": "bind", "sessionId": judge["sessionId"], "stationId": "station-01"},
            {"type": "bind", "sessionId": judge["sessionId"], "stationId": "station-01", "token": other["accessToken"]},
            {"type": "bind", "sessionId": judge["sessionId"], "stationId": "station-02", "token": judge["accessToken"]},
        ):
            with client.websocket_connect("/ws") as ws:
                assert ws.receive_json()["payload"]["message"] == "connected"
                ws.send_json(bind)
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()
                assert closed.value.code == 1008

        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json(
                {"type": "bind", "sessionId": judge["sessionId"], "stationId": "station-01", "token": judge["accessToken"]}
            )
            bound = ws.receive_json()
            assert bound["payload"]["message"] == "bound"


def test_websocket_judge_signals_need_a_connection_bound_to_that_session(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _logout(client)
        judge = _connect(client, "Judge 1", "device-1")

        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json(
                {
                    "type": "judge_round_completed",
                    "payload": {
                        "matchId": "m",
                        "roundNumber": 1,
                        "sessionId": judge["sessionId"],
                        "stationId": "station-01",
                        "judgeName": "Judge 1",
                    },
                }
            )
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008


def test_websocket_ping_gets_one_pong_and_pong_gets_no_answer(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _logout(client)
        judge = _connect(client, "Judge 1", "device-1")

        with client.websocket_connect(
            f"/ws?sessionId={judge['sessionId']}&stationId=station-01&token={judge['accessToken']}"
        ) as ws:
            for _ in range(3):
                ws.receive_json()
            ws.send_json({"type": "pong", "payload": {}})
            ws.send_json({"type": "ping", "payload": {}})
            # The pong was not answered: the next message is the reply to the ping.
            reply = ws.receive_json()
            assert reply["type"] == "pong"
            ws.send_json({"type": "unknown-probe"})
            assert ws.receive_json()["payload"]["message"] == "unknown message type"


def test_session_replacement_revokes_the_old_device_and_keeps_one_judge(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        _logout(client)
        first = _connect(client, "Judge 1", "device-1")

        conflict = client.post(
            "/stations/connect",
            json={"stationId": "station-01", "judgeName": "Judge 1", "credential": "1234", "deviceId": "device-2"},
        )
        assert conflict.status_code == 409

        with client.websocket_connect(
            f"/ws?sessionId={first['sessionId']}&stationId=station-01&token={first['accessToken']}"
        ) as old_device:
            for _ in range(3):
                old_device.receive_json()
            second = _connect(client, "Judge 1", "device-2", replaceExistingJudgeSession=True)
            notices = [old_device.receive_json(), old_device.receive_json()]
        assert {item["type"] for item in notices} == {"judge_kicked", "session_revoked"}
        assert all(item["payload"]["sessionId"] == first["sessionId"] for item in notices)

        assert client.get("/health", headers=_bearer(first)).status_code == 401
        assert client.get("/stations/station-01/active-session", headers=_bearer(second)).json()[
            "active_sessions_count"
        ] == 1
        # snake_case is accepted too.
        third = _connect(client, "Judge 1", "device-3", replace_existing_judge_session=True)
        assert third["sessionId"] not in (first["sessionId"], second["sessionId"])


def test_score_event_after_the_operator_closed_the_match_is_409_match_closed(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        _station(client)
        judge = _connect(client, "Judge 1", "device-1")
        started = client.post(
            "/admin/stations/station-01/matches/start",
            data={
                "competitor_left_name": "Red Athlete",
                "competitor_right_name": "Blue Athlete",
                "category_id": "advanced",
                "selected_poomsaes": ["Taeguk 5", "Taeguk 6", "Taeguk 7"],
                "total_rounds": "2",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert started.status_code == 303
        match_id = client.get("/stations/station-01/active-match-state", headers=_bearer(judge)).json()["matchId"]
        accepted = client.post("/score-events", json=_score_event(match_id, judge, "Judge 1", 1), headers=_bearer(judge))
        assert accepted.status_code == 200

        closed = client.post("/admin/stations/station-01/active-match/finalize", data={"actor": "admin"}, follow_redirects=False)
        assert closed.status_code == 303

        late = client.post("/score-events", json=_score_event(match_id, judge, "Judge 1", 2), headers=_bearer(judge))
        assert late.status_code == 409
        assert late.json()["code"] == "match_closed"
