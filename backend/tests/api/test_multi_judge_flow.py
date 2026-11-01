"""End-to-end: several judges score and finalize one shared match started from the admin panel."""

import hashlib
import json
import os
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from tkd_scorer.infra.config.settings import get_settings

ADMIN_PASSWORD = "multi-judge-admin"
TECHNIQUE = "TECHNIQUE"
SPEED = "PRESENTATION_SPEED_POWER"
RHYTHM = "PRESENTATION_RHYTHM_TEMPO"
ENERGY = "PRESENTATION_ENERGY_EXPRESSION"


def _client(tmp_path: Path) -> TestClient:
    os.environ["TKD_DATABASE_URL"] = f"sqlite:///{tmp_path / 'multi_judge.db'}"
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


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _judge_card(plan: list[tuple[int, str, str, str]]) -> dict[int, dict[str, Decimal]]:
    """What the judge app shows: technique from 4.0, three presentation categories from 2.0 (min 0, max 2.0)."""
    card: dict[int, dict[str, Decimal]] = {}
    for round_number in (1, 2):
        values = {("red", TECHNIQUE): Decimal("4.0"), ("blue", TECHNIQUE): Decimal("4.0")}
        for side in ("red", "blue"):
            for target in (SPEED, RHYTHM, ENERGY):
                values[(side, target)] = Decimal("2.0")
        for item_round, side, target, delta in plan:
            if item_round != round_number:
                continue
            maximum = Decimal("4.0") if target == TECHNIQUE else Decimal("2.0")
            values[(side, target)] = min(maximum, max(Decimal("0"), values[(side, target)] + Decimal(delta)))
        card[round_number] = {
            f"technique_{side}": values[(side, TECHNIQUE)] for side in ("red", "blue")
        } | {
            f"presentation_{side}": sum(values[(side, target)] for target in (SPEED, RHYTHM, ENERGY))
            for side in ("red", "blue")
        }
    return card


def _final_score(card: dict[int, dict[str, Decimal]], side: str) -> Decimal:
    rounds = list(card.values())
    technique = _round2(sum(item[f"technique_{side}"] for item in rounds) / len(rounds))
    presentation = _round2(sum(item[f"presentation_{side}"] for item in rounds) / len(rounds))
    return technique + presentation


def _fmt(value: Decimal) -> str:
    return str(_round2(value))


def _checksum(*, match_id: str, judge: dict, card: dict, total_events: int, last_sequence: int) -> str:
    payload = {
        "matchId": match_id,
        "sessionId": judge["sessionId"],
        "stationId": "station-01",
        "judgeName": judge["name"],
        "totalEvents": total_events,
        "lastSequence": last_sequence,
        "finalScoreRed": _fmt(_final_score(card, "red")),
        "finalScoreBlue": _fmt(_final_score(card, "blue")),
        "rounds": [
            {
                "roundNumber": number,
                "techniqueRed": _fmt(values["technique_red"]),
                "presentationRed": _fmt(values["presentation_red"]),
                "techniqueBlue": _fmt(values["technique_blue"]),
                "presentationBlue": _fmt(values["presentation_blue"]),
            }
            for number, values in sorted(card.items())
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _setup_station_and_judges(client: TestClient, count: int) -> list[dict]:
    login = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "next": "/admin"}, follow_redirects=False)
    assert login.status_code == 303
    created = client.post(
        "/admin/stations/create",
        data={"station_name": "Station 01", "station_id": "station-01", "credential": "1234", "actor": "test"},
        follow_redirects=False,
    )
    assert created.status_code == 303

    judges = []
    for index in range(count):
        name = f"Judge {index + 1}"
        connected = client.post(
            "/stations/connect",
            json={"stationId": "station-01", "judgeName": name, "credential": "1234", "deviceId": f"device-{index}"},
        )
        assert connected.status_code == 200
        body = connected.json()
        judges.append({"name": name, "sessionId": body["sessionId"], "token": body["accessToken"]})
    return judges


def _start_match(client: TestClient, judges: list[dict]) -> str:
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
    state = client.get(
        "/stations/station-01/active-match-state",
        headers={"Authorization": f"Bearer {judges[0]['token']}"},
    ).json()
    assert state["hasActiveMatch"] is True
    return state["matchId"]


def _post_events_interleaved(client: TestClient, match_id: str, judges: list[dict], plans: list[list]) -> list[int]:
    """Round-robin across judges; each judge numbers its own events 1..n (sequences collide across judges)."""
    sequences = [0] * len(judges)
    longest = max(len(plan) for plan in plans)
    for position in range(longest):
        for index, judge in enumerate(judges):
            if position >= len(plans[index]):
                continue
            round_number, side, target, delta = plans[index][position]
            sequences[index] += 1
            key = f"{judge['sessionId']}-{sequences[index]}"
            response = client.post(
                "/score-events",
                json={
                    "eventId": key,
                    "idempotencyKey": key,
                    "sessionId": judge["sessionId"],
                    "stationId": "station-01",
                    "matchId": match_id,
                    "roundNumber": round_number,
                    "athleteSide": side.upper(),
                    "scoreTarget": target,
                    "scoreDelta": float(delta),
                    "occurredAt": "2026-03-18T12:00:00Z",
                    "sequence": sequences[index],
                    "judgeName": judge["name"],
                },
                headers={"Authorization": f"Bearer {judge['token']}", "Idempotency-Key": key},
            )
            assert response.status_code == 200, response.text
    return sequences


def _finalize(client: TestClient, match_id: str, judge: dict, plan: list, last_sequence: int):
    card = _judge_card(plan)
    return client.post(
        "/matches/finalize",
        json={
            "sessionId": judge["sessionId"],
            "stationId": "station-01",
            "matchId": match_id,
            "judgeName": judge["name"],
            "competitorLeftName": "Red Athlete",
            "competitorRightName": "Blue Athlete",
            "totalRounds": 2,
            "finalRound": 2,
            "finalScoreRed": float(_final_score(card, "red")),
            "finalScoreBlue": float(_final_score(card, "blue")),
            "totalEvents": len(plan),
            "finalSequence": last_sequence,
            "startedAt": "2026-03-18T12:00:00.000Z",
            "finishedAt": "2026-03-18T12:10:00.000Z",
            "checksum": _checksum(
                match_id=match_id, judge=judge, card=card, total_events=len(plan), last_sequence=last_sequence
            ),
            "roundsSummary": [
                {
                    "roundNumber": number,
                    "techniqueRed": float(values["technique_red"]),
                    "presentationRed": float(values["presentation_red"]),
                    "techniqueBlue": float(values["technique_blue"]),
                    "presentationBlue": float(values["presentation_blue"]),
                    "red": float(values["technique_red"] + values["presentation_red"]),
                    "blue": float(values["technique_blue"] + values["presentation_blue"]),
                }
                for number, values in sorted(card.items())
            ],
        },
        headers={"Authorization": f"Bearer {judge['token']}"},
    )


def _match_status(client: TestClient, match_id: str) -> str:
    return client.get(f"/matches/{match_id}/summary").json()["status"]


def _side_table(html: str, side: str) -> str:
    match = re.search(rf'data-side-scorecard="{side}">(.*?)</table>', html, re.S)
    assert match, f"no scorecard table for {side}"
    return match.group(1)


def _round_block(table: str, round_number: int) -> str:
    match = re.search(rf'<tbody data-round="{round_number}">(.*?)</tbody>', table, re.S)
    assert match, f"no round {round_number}"
    return match.group(1)


def _consolidated(block: str, row: str) -> str:
    match = re.search(rf'data-consolidated="{row}">\s*([^<\s]+)\s*<', block)
    assert match, f"no consolidated {row}"
    return match.group(1)


def _judge_values(block: str, row: str) -> list[str]:
    row_html = re.search(rf'<tr data-row="{row}">(.*?)</tr>', block, re.S)
    assert row_html
    return re.findall(r'data-judge-alias="J\d+">\s*([^<\s]+)\s*<', row_html.group(1))


def _side_total(html: str, side: str) -> str:
    match = re.search(rf'data-side="{side}">.*?data-score="total">\s*([^<\s]+)\s*<', html, re.S)
    assert match
    return match.group(1)


THREE_JUDGE_PLANS = [
    [
        (1, "red", TECHNIQUE, "-0.3"),
        (1, "red", SPEED, "-0.2"),
        (1, "red", TECHNIQUE, "-0.1"),
        (1, "blue", TECHNIQUE, "-0.1"),
        (2, "red", TECHNIQUE, "-0.5"),
        (2, "red", RHYTHM, "-0.3"),
        (2, "blue", TECHNIQUE, "-0.3"),
        (2, "blue", ENERGY, "-0.1"),
    ],
    [
        (1, "red", TECHNIQUE, "-0.2"),
        (1, "red", ENERGY, "-0.4"),
        (1, "blue", TECHNIQUE, "-0.4"),
        (1, "blue", SPEED, "-0.2"),
        (2, "red", TECHNIQUE, "-0.1"),
        (2, "blue", TECHNIQUE, "-0.2"),
        (2, "blue", RHYTHM, "-0.5"),
    ],
    [
        (1, "red", TECHNIQUE, "-0.4"),
        (1, "red", SPEED, "-0.1"),
        (1, "red", RHYTHM, "-0.1"),
        (1, "blue", TECHNIQUE, "-0.2"),
        (2, "red", TECHNIQUE, "-0.3"),
        (2, "red", ENERGY, "-0.2"),
        (2, "blue", TECHNIQUE, "-0.1"),
        (2, "blue", SPEED, "-0.3"),
    ],
]


def test_three_judges_score_and_finalize_one_shared_match(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        judges = _setup_station_and_judges(client, 3)
        match_id = _start_match(client, judges)
        sequences = _post_events_interleaved(client, match_id, judges, THREE_JUDGE_PLANS)

        live = client.get("/scoreboard/station-01/live")
        assert live.status_code == 200
        red = _side_table(live.text, "red")
        assert re.findall(r'<th[^>]*data-judge-alias="(J\d+)"', red) == ["J1", "J2", "J3"]
        assert _judge_values(_round_block(red, 1), "technique") == ["3.6", "3.8", "3.6"]
        assert _judge_values(_round_block(red, 1), "presentation") == ["5.8", "5.6", "5.8"]

        responses = []
        for index, judge in enumerate(judges):
            assert _match_status(client, match_id) == "in_progress"
            response = _finalize(client, match_id, judge, THREE_JUDGE_PLANS[index], sequences[index])
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["reconciled"] is True, body["notes"]
            assert body["checksumVerified"] is True
            assert body["judgesFinalized"] == index + 1
            assert body["judgesRequired"] == 3
            responses.append(body)
        assert [item["matchStatus"] for item in responses] == ["in_progress", "in_progress", "finished"]
        assert _match_status(client, match_id) == "finished"

        board = client.get("/scoreboard/station-01/live").text
        red = _side_table(board, "red")
        blue = _side_table(board, "blue")
        assert _consolidated(_round_block(red, 1), "technique") == "3.67"
        assert _consolidated(_round_block(red, 1), "presentation") == "5.73"
        assert _consolidated(_round_block(red, 1), "score") == "9.40"
        assert _consolidated(_round_block(red, 2), "score") == "9.53"
        assert _consolidated(_round_block(blue, 1), "technique") == "3.77"
        assert _consolidated(_round_block(blue, 1), "presentation") == "5.93"
        assert _consolidated(_round_block(blue, 2), "score") == "9.50"
        assert _side_total(board, "red") == "9.47"
        assert _side_total(board, "blue") == "9.60"
        assert board.count('data-judge-status="finalized"') == 3
        assert "js-winner-overlay" in board

        # The first judge retries its finalization (released session, new request): same answer, no 422/401.
        again = _finalize(client, match_id, judges[0], THREE_JUDGE_PLANS[0], sequences[0])
        assert again.status_code == 200, again.text
        replay = again.json()
        assert replay["idempotent_replay"] is True
        for key in ("status", "reconciled", "notes", "serverFinalScoreRed", "serverFinalScoreBlue", "matchStatus"):
            assert replay[key] == responses[0][key], key

        results = client.get("/admin/results").text
        assert "9.47" in results and "9.60" in results


FIVE_JUDGE_ROUND_ONE_RED = [
    # TEC 2.9, 3.1, 3.0, 3.4, 2.5 -> 3.00 ; PRES 5.2, 5.0, 5.6, 4.8, 5.1 -> 5.10 (worked example).
    [(1, "red", TECHNIQUE, "-1.1"), (1, "red", SPEED, "-0.8")],
    [(1, "red", TECHNIQUE, "-0.9"), (1, "red", SPEED, "-0.5"), (1, "red", RHYTHM, "-0.5")],
    [(1, "red", TECHNIQUE, "-1.0"), (1, "red", ENERGY, "-0.4")],
    [(1, "red", TECHNIQUE, "-0.6"), (1, "red", SPEED, "-0.6"), (1, "red", RHYTHM, "-0.6")],
    [(1, "red", TECHNIQUE, "-1.5"), (1, "red", ENERGY, "-0.9")],
]


def test_five_judges_trim_highest_and_lowest_per_part(tmp_path: Path) -> None:
    plans = [
        [*plan, (1, "blue", TECHNIQUE, f"-0.{index + 1}"), (2, "red", TECHNIQUE, "-0.2"), (2, "blue", SPEED, "-0.1")]
        for index, plan in enumerate(FIVE_JUDGE_ROUND_ONE_RED)
    ]
    with _client(tmp_path) as client:
        judges = _setup_station_and_judges(client, 5)
        match_id = _start_match(client, judges)
        sequences = _post_events_interleaved(client, match_id, judges, plans)

        for index, judge in enumerate(judges):
            assert _match_status(client, match_id) == "in_progress"
            response = _finalize(client, match_id, judge, plans[index], sequences[index])
            assert response.status_code == 200, response.text
            assert response.json()["reconciled"] is True, response.json()["notes"]
        assert _match_status(client, match_id) == "finished"

        board = client.get("/scoreboard/station-01/live").text
        red = _side_table(board, "red")
        blue = _side_table(board, "blue")
        assert re.findall(r'<th[^>]*data-judge-alias="(J\d+)"', red) == ["J1", "J2", "J3", "J4", "J5"]
        assert _consolidated(_round_block(red, 1), "technique") == "3.00"
        assert _consolidated(_round_block(red, 1), "presentation") == "5.10"
        assert _consolidated(_round_block(red, 1), "score") == "8.10"
        # Blue round 1 technique 3.9, 3.8, 3.7, 3.6, 3.5 -> drop 3.9 and 3.5 -> 3.70.
        assert _consolidated(_round_block(blue, 1), "technique") == "3.70"
        # Round 2: red 3.8 + 6.0 = 9.80 for everyone; match red = (8.10 + 9.80) / 2 = 8.95.
        assert _consolidated(_round_block(red, 2), "score") == "9.80"
        assert _side_total(board, "red") == "8.95"


def test_kicked_judge_is_shown_removed_and_the_match_closes_with_the_others(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        judges = _setup_station_and_judges(client, 3)
        match_id = _start_match(client, judges)
        sequences = _post_events_interleaved(client, match_id, judges, THREE_JUDGE_PLANS)
        for index in (0, 1):
            response = _finalize(client, match_id, judges[index], THREE_JUDGE_PLANS[index], sequences[index])
            assert response.json()["reconciled"] is True, response.json()["notes"]
        assert _match_status(client, match_id) == "in_progress"

        kick = client.post(
            f"/admin/stations/station-01/sessions/{judges[2]['sessionId']}/kick",
            data={"reason": "removed", "actor": "test"},
            follow_redirects=False,
        )
        assert kick.status_code == 303

        assert _match_status(client, match_id) == "finished"
        board = client.get("/scoreboard/station-01/live").text
        assert board.count('data-judge-status="finalized"') == 2
        assert board.count('data-judge-status="removed"') == 1
        assert "Finalized 2/2" in board
        # Round 1 red technique of J1 and J2 only: (3.6 + 3.8) / 2.
        assert _consolidated(_round_block(_side_table(board, "red"), 1), "technique") == "3.70"
        debug = client.get("/admin/stations/station-01/scoreboard/debug").text
        assert 'data-judge-status="removed"' in debug
