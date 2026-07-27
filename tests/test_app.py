from datetime import date, timedelta

import pytest

import app as app_module


AUTH = {"Authorization": "Bearer test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("OURA_USER_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("OURA_MAX_AGE_DAYS", "2")
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def valid_prep_payload():
    return {
        "match_type": "singles",
        "opponent_name": "Андрей",
        "opponent_level": "равный",
        "opponent_style": "контратакует",
        "surface": "hard",
        "weather": "тепло",
        "session_format": "friendly",
        "energy_level": 3,
        "last_meal": "обед два часа назад",
        "physical_state": "всё нормально",
        "mindset": "спокоен",
        "use_oura": True,
    }


def active_bundle(status="in_progress"):
    return {
        "match": {"id": "match-1", "status": status, "current_score": {"sets": "", "game": "0-0", "serving": "unknown"}},
        "prep": {"generated_brief": "Бриф"},
        "events": [],
    }


def test_health_does_not_require_auth(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_protected_route_requires_auth(client):
    response = client.get("/api/matches")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_latest_oura_marks_old_record_as_stale(client, mocker):
    old_date = (date.today() - timedelta(days=4)).isoformat()
    mocker.patch("app.db.get_latest_oura_log", return_value={
        "id": "log-1", "date": old_date, "readiness_score": 72,
        "sleep_score": 76, "average_hrv": 43.5,
    })

    response = client.get("/api/oura/latest", headers=AUTH)

    assert response.status_code == 200
    assert response.get_json()["oura"]["is_stale"] is True
    assert response.get_json()["oura"]["average_hrv"] == 43.5


def test_create_prep_generates_before_creating_match(client, mocker):
    mocker.patch("app.db.get_active_match", return_value=None)
    mocker.patch("app.db.get_latest_oura_log", return_value={
        "id": "log-1", "date": date.today().isoformat(), "readiness_score": 82,
        "sleep_score": 79, "average_hrv": 48.0,
    })
    generate = mocker.patch("app.gpt.generate_prep_brief", return_value="Глубоко играй под бэкхэнд.")
    create = mocker.patch("app.db.create_match", return_value={"id": "match-1", "status": "preparing"})
    mocker.patch("app.db.save_prep", return_value={"id": "prep-1", "generated_brief": "Глубоко играй под бэкхэнд."})

    response = client.post("/api/matches/prep", headers=AUTH, json=valid_prep_payload())

    assert response.status_code == 201
    assert response.get_json()["match"]["id"] == "match-1"
    assert generate.call_count == 1
    assert create.call_count == 1


def test_active_match_prevents_second_prep_and_ai_cost(client, mocker):
    mocker.patch("app.db.get_active_match", return_value={"id": "existing"})
    generate = mocker.patch("app.gpt.generate_prep_brief")

    response = client.post("/api/matches/prep", headers=AUTH, json=valid_prep_payload())

    assert response.status_code == 409
    generate.assert_not_called()


def test_invalid_prep_value_returns_400(client, mocker):
    mocker.patch("app.db.get_active_match", return_value=None)
    payload = valid_prep_payload()
    payload["surface"] = "ice"

    response = client.post("/api/matches/prep", headers=AUTH, json=payload)

    assert response.status_code == 400


def test_event_reuses_existing_idempotent_result(client, mocker):
    mocker.patch("app.db.get_match_bundle", return_value=active_bundle())
    mocker.patch("app.db.get_event_by_idempotency_key", return_value={
        "id": "event-1", "generated_advice": "Играй глубже.",
    })
    generate = mocker.patch("app.gpt.generate_changeover_advice")

    response = client.post("/api/matches/match-1/events", headers=AUTH, json={
        "idempotency_key": "00000000-0000-0000-0000-000000000010",
        "event_type": "changeover",
        "working_well": ["serve"],
        "not_working": [],
        "how_feeling": "нормально",
        "score": {"sets": "3-2", "game": "0-0", "serving": "self"},
    })

    assert response.status_code == 200
    assert response.get_json()["deduplicated"] is True
    generate.assert_not_called()


def test_new_set_requires_energy(client, mocker):
    mocker.patch("app.db.get_match_bundle", return_value=active_bundle())
    mocker.patch("app.db.get_event_by_idempotency_key", return_value=None)

    response = client.post("/api/matches/match-1/events", headers=AUTH, json={
        "idempotency_key": "00000000-0000-0000-0000-000000000011",
        "event_type": "new_set",
        "working_well": ["serve"],
        "not_working": ["backhand"],
        "how_feeling": "устал",
        "score": {"sets": "4-6", "game": "0-0", "serving": "opponent"},
    })

    assert response.status_code == 400


def test_changeover_event_receives_full_match_context(client, mocker):
    bundle = active_bundle()
    bundle["events"] = [{"id": "older-event", "generated_advice": "Играй глубже"}]
    mocker.patch("app.db.get_match_bundle", return_value=bundle)
    mocker.patch("app.db.get_event_by_idempotency_key", return_value=None)
    generate = mocker.patch("app.gpt.generate_changeover_advice", return_value="Подавай в корпус.")
    mocker.patch("app.db.add_event", return_value={"id": "event-2", "generated_advice": "Подавай в корпус."})
    update_score = mocker.patch("app.db.update_score", return_value=bundle["match"])

    response = client.post("/api/matches/match-1/events", headers=AUTH, json={
        "idempotency_key": "00000000-0000-0000-0000-000000000012",
        "event_type": "changeover",
        "working_well": ["serve"],
        "not_working": ["return"],
        "how_feeling": "спокоен",
        "score": {"sets": "4-3", "game": "0-0", "serving": "self"},
    })

    assert response.status_code == 201
    context = generate.call_args.args[0]
    assert context["prep"]["generated_brief"] == "Бриф"
    assert context["previous_events"][0]["id"] == "older-event"
    update_score.assert_called_once()


def test_start_match_changes_state(client, mocker):
    mocker.patch("app.db.start_match", return_value={"id": "match-1", "status": "in_progress"})

    response = client.post("/api/matches/match-1/start", headers=AUTH, json={})

    assert response.status_code == 200
    assert response.get_json()["match"]["status"] == "in_progress"


def test_cors_echoes_only_allowed_origin(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_ORIGIN", "https://example.github.io")

    allowed = client.get("/api/health", headers={"Origin": "https://example.github.io"})
    rejected = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["Access-Control-Allow-Origin"] == "https://example.github.io"
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_unknown_route_stays_404(client):
    response = client.get("/not-a-route")
    assert response.status_code == 404
