import os
from pathlib import Path

from fastapi.testclient import TestClient

from tkd_scorer.infra.config.settings import get_settings


def _build_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "api_test.db"
    os.environ["TKD_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TKD_JWT_SECRET_KEY"] = "test-jwt-secret"
    os.environ["TKD_ADMIN_PASSWORD"] = ""
    os.environ["TKD_ADMIN_BASE_PATH"] = "/admin"
    os.environ["TKD_ADMIN_IP_ALLOWLIST"] = ""
    os.environ["TKD_ADMIN_SECURITY_FAIL_FAST"] = "false"
    os.environ["TKD_ADMIN_TRUST_PROXY_HEADERS"] = "false"
    os.environ["TKD_UI_LANGUAGE"] = "en"
    get_settings.cache_clear()

    from tkd_scorer.entry_points.fastapi.app import create_app

    app = create_app()
    return TestClient(app)


def test_health_and_station_connect_flow(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        bootstrap = client.post(
            "/bootstrap/generate",
            json={
                "stationId": "station-01",
                "stationName": "Station 01",
                "tournamentId": "tkd-2026",
            },
        )
        assert bootstrap.status_code == 200
        assert bootstrap.json()["expiresAt"].endswith("Z")
        assert bootstrap.json()["stationId"] == "station-01"
        assert bootstrap.json()["stationName"] == "Station 01"

        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        stations = client.get("/stations/active")
        assert stations.status_code == 200
        assert len(stations.json()) >= 1

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
            headers={"Authorization": f"Bearer {bootstrap.json()['bootstrapToken']}"},
        )
        assert connect.status_code == 200
        payload = connect.json()
        assert payload["sessionId"]
        assert payload["accessToken"]

        restore = client.post(
            "/sessions/restore",
            json={"accessToken": payload["accessToken"]},
        )
        assert restore.status_code == 200
        assert restore.json()["sessionId"] == payload["sessionId"]


def test_match_and_score_event_endpoints_are_idempotent(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        match = client.post(
            "/matches",
            json={
                "stationId": "station-01",
                "sessionId": connect["sessionId"],
                "judgeName": "Judge 1",
                "competitorLeftName": "Competitor A",
                "competitorRightName": "Competitor B",
                "totalRounds": 2,
                "startingScore": "10.0",
            },
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert match.status_code == 200
        match_id = match.json()["id"]

        event_body = {
            "eventId": "event-1",
            "idempotencyKey": "idem-1",
            "sessionId": connect["sessionId"],
            "stationId": "station-01",
            "matchId": match_id,
            "roundNumber": 1,
            "athleteSide": "RED",
            "scoreTarget": "TECHNIQUE",
            "scoreDelta": "-0.1",
            "occurredAt": "2026-03-18T12:00:00Z",
            "sequence": 1,
            "judgeName": "Judge 1",
        }

        auth = {"Authorization": f"Bearer {connect['accessToken']}", "Idempotency-Key": "idem-1"}
        first = client.post("/score-events", json=event_body, headers=auth)
        second = client.post("/score-events", json=event_body, headers=auth)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["idempotent_replay"] is False
        assert second.json()["idempotent_replay"] is True

        summary = client.get(
            f"/matches/{match_id}/summary", headers={"Authorization": f"Bearer {connect['accessToken']}"}
        )
        assert summary.status_code == 200
        assert summary.json()["total_events"] == 1


def test_finalize_endpoint_requires_existing_backend_match_id(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        match = client.post(
            "/matches",
            json={
                "stationId": "station-01",
                "sessionId": connect["sessionId"],
                "judgeName": "Judge 1",
                "competitorLeftName": "Competitor A",
                "competitorRightName": "Competitor B",
                "totalRounds": 2,
                "startingScore": "10.0",
            },
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert match.status_code == 200

        finalize = client.post(
            "/matches/finalize",
            json={
                "sessionId": connect["sessionId"],
                "stationId": "station-01",
                "matchId": "mobile-local-match-id",
                "judgeName": "Judge 1",
                "competitorLeftName": "Competitor A",
                "competitorRightName": "Competitor B",
                "totalRounds": 2,
                "finalRound": 1,
                "finalScoreLeft": "10.0",
                "finalScoreRight": "10.0",
                "totalEvents": 0,
                "lastSequence": 0,
                "startedAt": "2026-03-18T12:00:00Z",
                "finishedAt": "2026-03-18T12:10:00Z",
                "checksum": "invalid",
                "idempotencyKey": "fin-api-fallback-by-session",
            },
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert finalize.status_code == 422
        assert "matchId must reference an existing backend match" in finalize.json()["detail"]


def test_station_active_match_state_endpoint_returns_active_match_json(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        match = client.post(
            "/matches",
            json={
                "stationId": "station-01",
                "sessionId": connect["sessionId"],
                "judgeName": "Judge 1",
                "competitorLeftName": "Red",
                "competitorRightName": "Blue",
                "totalRounds": 2,
                "startingScore": "10.0",
            },
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert match.status_code == 200
        match_id = match.json()["id"]

        response = client.get(
            "/stations/station-01/active-match-state",
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["hasActiveMatch"] is True
        assert payload["matchId"] == match_id
        assert payload["competitorRedName"] == "Red"
        assert payload["competitorBlueName"] == "Blue"
        assert payload["updatedAt"].endswith("Z")


def test_station_active_match_state_endpoint_returns_false_without_active_match(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        response = client.get(
            "/stations/station-01/active-match-state",
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["hasActiveMatch"] is False
        assert payload["matchId"] is None
        assert payload["competitorRedName"] is None
        assert payload["competitorBlueName"] is None
        assert payload["updatedAt"].endswith("Z")


def test_station_active_match_state_endpoint_requires_bearer_token(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        response = client.get("/stations/station-01/active-match-state")
        assert response.status_code == 401


def test_station_active_match_state_endpoint_returns_404_for_unknown_station(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        response = client.get(
            "/stations/inexistente/active-match-state",
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert response.status_code == 404


def test_websocket_initial_contract_events_are_emitted_on_bind(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        with client.websocket_connect(
            f"/ws?sessionId={connect['sessionId']}&stationId=station-01&token={connect['accessToken']}"
        ) as ws:
            server_notice = ws.receive_json()
            assert server_notice["eventType"] == "server_notice"

            judge_settings = ws.receive_json()
            assert judge_settings["eventType"] == "judge_settings_updated"
            payload = judge_settings["payload"]
            assert payload["defaultRounds"] == 2
            assert payload["defaultStartingScore"] == 4.0
            assert payload["presentationCategoryStartScore"] == 2.0
            assert payload["actionValue1"] == 0.1
            assert payload["actionValue2"] == 0.3

            active_match_state = ws.receive_json()
            assert active_match_state["eventType"] == "active_match_state"
            assert active_match_state["payload"]["hasActiveMatch"] is False


def test_websocket_accepts_judge_operational_signals_and_notifies_station(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        match_response = client.post(
            "/matches",
            json={
                "stationId": "station-01",
                "sessionId": connect["sessionId"],
                "judgeName": "Judge 1",
                "competitorLeftName": "Red",
                "competitorRightName": "Blue",
                "totalRounds": 2,
                "startingScore": "10.0",
            },
            headers={"Authorization": f"Bearer {connect['accessToken']}"},
        )
        assert match_response.status_code == 200
        match_id = match_response.json()["id"]

        with client.websocket_connect(
            f"/ws?sessionId={connect['sessionId']}&stationId=station-01&token={connect['accessToken']}&deviceId=device-1"
        ) as ws:
            # Initial contract events
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()

            ws.send_json(
                {
                    "type": "judge_round_completed",
                    "payload": {
                        "matchId": match_id,
                        "roundNumber": 1,
                        "sessionId": connect["sessionId"],
                        "stationId": "station-01",
                        "judgeName": "Judge 1",
                        "deviceId": "device-1",
                        "finishedAt": "2026-03-20T15:00:00.000Z",
                    },
                }
            )

            round_events = [ws.receive_json(), ws.receive_json()]
            round_event_types = {item["eventType"] for item in round_events}
            assert "match_updated" in round_event_types
            assert "server_notice" in round_event_types
            round_update = next(item for item in round_events if item["eventType"] == "match_updated")
            assert round_update["payload"]["updateType"] == "judge_round_completed"
            assert round_update["payload"]["matchId"] == match_id
            assert round_update["payload"]["roundNumber"] == 1

            ws.send_json(
                {
                    "type": "judge_match_completed",
                    "payload": {
                        "matchId": match_id,
                        "finalRound": 2,
                        "checksum": "sha256-demo",
                        "sessionId": connect["sessionId"],
                        "stationId": "station-01",
                        "judgeName": "Judge 1",
                        "deviceId": "device-1",
                        "finishedAt": "2026-03-20T15:05:00.000Z",
                    },
                }
            )

            match_events = [ws.receive_json(), ws.receive_json()]
            match_event_types = {item["eventType"] for item in match_events}
            assert "match_updated" in match_event_types
            assert "server_notice" in match_event_types
            match_update = next(item for item in match_events if item["eventType"] == "match_updated")
            assert match_update["payload"]["updateType"] == "judge_match_completed"
            assert match_update["payload"]["matchId"] == match_id
            assert match_update["payload"]["finalRound"] == 2


def test_websocket_active_match_state_ignores_match_from_revoked_session(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect_1 = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        match = client.post(
            "/matches",
            json={
                "stationId": "station-01",
                "sessionId": connect_1["sessionId"],
                "judgeName": "Judge 1",
                "competitorLeftName": "Competitor A",
                "competitorRightName": "Competitor B",
                "totalRounds": 2,
                "startingScore": "10.0",
            },
            headers={"Authorization": f"Bearer {connect_1['accessToken']}"},
        )
        assert match.status_code == 200

        kick = client.post(
            f"/admin/stations/station-01/sessions/{connect_1['sessionId']}/kick",
            data={"reason": "disconnected_cleanup", "actor": "test"},
            follow_redirects=False,
        )
        assert kick.status_code == 303

        connect_2 = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-2",
            },
        ).json()

        with client.websocket_connect(
            f"/ws?sessionId={connect_2['sessionId']}&stationId=station-01&token={connect_2['accessToken']}"
        ) as ws:
            ws.receive_json()  # server_notice
            ws.receive_json()  # judge_settings_updated
            active_match_state = ws.receive_json()
            assert active_match_state["eventType"] == "active_match_state"
            assert active_match_state["payload"]["hasActiveMatch"] is False


def test_websocket_disconnect_keeps_session_valid_for_reconnect(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        connect = client.post(
            "/stations/connect",
            json={
                "stationId": "station-01",
                "judgeName": "Judge 1",
                "credential": "1234",
                "deviceId": "device-1",
            },
        ).json()

        before = client.get(
            "/stations/station-01/active-session", headers={"Authorization": f"Bearer {connect['accessToken']}"}
        )
        assert before.status_code == 200
        assert before.json()["active_sessions_count"] == 1

        with client.websocket_connect(
            f"/ws?sessionId={connect['sessionId']}&stationId=station-01&token={connect['accessToken']}"
        ) as ws:
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()

        after = client.get(
            "/stations/station-01/active-session", headers={"Authorization": f"Bearer {connect['accessToken']}"}
        )
        assert after.status_code == 200
        assert after.json()["active_sessions_count"] == 1
        assert after.json()["session_id"] == connect["sessionId"]

        with client.websocket_connect(
            f"/ws?sessionId={connect['sessionId']}&stationId=station-01&token={connect['accessToken']}"
        ) as ws_reconnect:
            server_notice = ws_reconnect.receive_json()
            assert server_notice["eventType"] == "server_notice"
