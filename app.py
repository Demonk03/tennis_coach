import hmac
import logging
import os
from datetime import date, datetime
from functools import wraps
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import db
import gpt

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TOPICS = {"forehand", "backhand", "serve", "return", "movement", "net"}
MATCH_TYPES = {"singles", "doubles"}
SURFACES = {"hard", "clay", "grass", "carpet", "other"}
SESSION_FORMATS = {"tournament", "1h_session", "2h_session", "friendly"}
SCORE_KEYS = {"sets", "game", "serving"}


class APIError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _allowed_origins() -> set[str]:
    configured = os.getenv("DASHBOARD_ORIGIN", "http://localhost:8000")
    return {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(APIError)
def handle_api_error(error: APIError):
    return jsonify({"error": {"code": error.code, "message": error.message}}), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    if isinstance(error, HTTPException):
        return jsonify({"error": {"code": "http_error", "message": error.description}}), error.code
    logger.exception("Unhandled API error")
    return jsonify({"error": {"code": "internal_error", "message": "Временная ошибка сервиса"}}), 500


def require_api_key(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        expected = os.getenv("API_KEY", "")
        auth = request.headers.get("Authorization", "")
        provided = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not expected or not hmac.compare_digest(provided, expected):
            raise APIError("Неверный API-ключ", 401, "unauthorized")
        return function(*args, **kwargs)

    return wrapper


def _json() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Ожидается JSON-объект")
    return payload


def _text(payload: dict[str, Any], field: str, *, required: bool = True, max_length: int = 300) -> str:
    value = payload.get(field, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise APIError(f"Поле {field} должно быть строкой")
    value = value.strip()
    if required and not value:
        raise APIError(f"Поле {field} обязательно")
    if len(value) > max_length:
        raise APIError(f"Поле {field} слишком длинное")
    return value


def _choice(payload: dict[str, Any], field: str, allowed: set[str]) -> str:
    value = _text(payload, field)
    if value not in allowed:
        raise APIError(f"Недопустимое значение поля {field}")
    return value


def _integer(payload: dict[str, Any], field: str, minimum: int, maximum: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise APIError(f"Поле {field} должно быть числом от {minimum} до {maximum}")
    return value


def _score(payload: dict[str, Any], field: str = "score") -> dict[str, str]:
    score = payload.get(field)
    if not isinstance(score, dict):
        raise APIError("Счёт должен быть объектом")
    clean = {key: str(score.get(key, "")).strip() for key in SCORE_KEYS}
    if not clean["sets"] and not clean["game"]:
        raise APIError("Укажите текущий счёт")
    if any(len(value) > 80 for value in clean.values()):
        raise APIError("Счёт слишком длинный")
    if clean["serving"] not in {"self", "opponent", "unknown"}:
        raise APIError("Некорректно указан подающий")
    return clean


def _valid_uuid(value: Any, field: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise APIError(f"Поле {field} должно быть UUID") from None


def _oura_snapshot() -> dict[str, Any] | None:
    user_id = os.getenv("OURA_USER_ID")
    if not user_id:
        return None
    row = db.get_latest_oura_log(user_id)
    if not row:
        return None
    try:
        data_date = date.fromisoformat(str(row["date"]))
        today = datetime.now(ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Moscow"))).date()
        age_days = max((today - data_date).days, 0)
    except (KeyError, ValueError):
        age_days = 999
    max_age = int(os.getenv("OURA_MAX_AGE_DAYS", "2"))
    return {
        "health_log_id": row.get("id"),
        "date": row.get("date"),
        "age_days": age_days,
        "is_stale": age_days > max_age,
        "readiness": row.get("readiness_score"),
        "sleep_score": row.get("sleep_score"),
        "average_hrv": row.get("average_hrv"),
        "average_heart_rate": row.get("average_heart_rate"),
        "total_sleep_duration": row.get("total_sleep_duration"),
        "activity_score": row.get("activity_score"),
    }


def _bundle_or_404(match_id: str) -> dict[str, Any]:
    bundle = db.get_match_bundle(match_id)
    if not bundle:
        raise APIError("Матч не найден", 404, "not_found")
    return bundle


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/oura/latest")
@require_api_key
def latest_oura():
    return jsonify({"oura": _oura_snapshot()})


@app.post("/api/matches/prep")
@require_api_key
def create_prep():
    payload = _json()
    if db.get_active_match():
        raise APIError("Сначала завершите или отмените активный матч", 409, "active_match_exists")

    match_data = {
        "match_type": _choice(payload, "match_type", MATCH_TYPES),
        "opponent_name": _text(payload, "opponent_name", required=False, max_length=100),
        "opponent_level": _text(payload, "opponent_level", max_length=100),
        "opponent_style": _text(payload, "opponent_style", required=False, max_length=200),
        "surface": _choice(payload, "surface", SURFACES),
        "weather": _text(payload, "weather", required=False, max_length=200),
        "session_format": _choice(payload, "session_format", SESSION_FORMATS),
    }
    survey = {
        "energy_level": _integer(payload, "energy_level", 1, 5),
        "last_meal": _text(payload, "last_meal", required=False, max_length=200),
        "physical_state": _text(payload, "physical_state", max_length=300),
        "mindset": _text(payload, "mindset", max_length=300),
    }
    oura = _oura_snapshot() if payload.get("use_oura", True) else None

    try:
        brief = gpt.generate_prep_brief(match_data, survey, oura)
    except Exception as error:
        logger.warning("Prep advice generation failed: %s", error)
        raise APIError("Не удалось получить бриф. Попробуйте ещё раз", 503, "ai_unavailable") from error

    match = db.create_match({**match_data, "status": "preparing"})
    try:
        prep = db.save_prep({
            "match_id": match["id"],
            "oura_health_log_id": oura.get("health_log_id") if oura else None,
            "oura_data_date": oura.get("date") if oura else None,
            "oura_is_stale": oura.get("is_stale", False) if oura else False,
            "oura_readiness": oura.get("readiness") if oura else None,
            "oura_sleep_score": oura.get("sleep_score") if oura else None,
            "oura_hrv": oura.get("average_hrv") if oura else None,
            **survey,
            "generated_brief": brief,
        })
    except Exception:
        db.cancel_match(match["id"])
        raise

    return jsonify({"match": match, "prep": prep, "brief": brief, "oura": oura}), 201


@app.get("/api/matches/active")
@require_api_key
def active_match():
    match = db.get_active_match()
    return jsonify({"active_match": db.get_match_bundle(match["id"]) if match else None})


@app.post("/api/matches/<match_id>/start")
@require_api_key
def start_match(match_id: str):
    match = db.start_match(match_id)
    if not match:
        raise APIError("Матч не найден или уже начат", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.patch("/api/matches/<match_id>/score")
@require_api_key
def update_score(match_id: str):
    score = _score(_json())
    match = db.update_score(match_id, score)
    if not match:
        raise APIError("Счёт можно менять только в активном матче", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.post("/api/matches/<match_id>/events")
@require_api_key
def create_event(match_id: str):
    payload = _json()
    bundle = _bundle_or_404(match_id)
    if bundle["match"]["status"] != "in_progress":
        raise APIError("Матч ещё не начат или уже завершён", 409, "invalid_match_state")

    idempotency_key = _valid_uuid(payload.get("idempotency_key"), "idempotency_key")
    existing = db.get_event_by_idempotency_key(idempotency_key)
    if existing:
        return jsonify({"event": existing, "advice": existing["generated_advice"], "deduplicated": True})

    event_type = _choice(payload, "event_type", {"changeover", "new_set"})
    working = payload.get("working_well", [])
    not_working = payload.get("not_working", [])
    if not isinstance(working, list) or not isinstance(not_working, list):
        raise APIError("Наблюдения должны быть списками")
    if not set(working).issubset(TOPICS) or not set(not_working).issubset(TOPICS):
        raise APIError("Неизвестная тема наблюдения")
    if set(working) & set(not_working):
        raise APIError("Одна тема не может одновременно идти и не идти")

    observation = {
        "event_type": event_type,
        "working_well": working,
        "not_working": not_working,
        "how_feeling": _text(payload, "how_feeling", max_length=200),
        "score": _score(payload),
    }
    energy_level = None
    if event_type == "new_set":
        energy_level = _integer(payload, "energy_level", 1, 5)
        observation["energy_level"] = energy_level

    context = {
        "match": bundle["match"],
        "prep": bundle["prep"],
        "previous_events": bundle["events"][-12:],
    }
    try:
        advice = (
            gpt.generate_changeover_advice(context, observation)
            if event_type == "changeover"
            else gpt.generate_new_set_advice(context, observation)
        )
    except Exception as error:
        logger.warning("Event advice generation failed: %s", error)
        raise APIError("Не удалось получить совет. Повторите запрос", 503, "ai_unavailable") from error

    event = db.add_event({
        "match_id": match_id,
        "idempotency_key": idempotency_key,
        "event_type": event_type,
        "working_well": working,
        "not_working": not_working,
        "how_feeling": observation["how_feeling"],
        "energy_level": energy_level,
        "score_at_event": observation["score"],
        "generated_advice": advice,
    })
    db.update_score(match_id, observation["score"])
    return jsonify({"event": event, "advice": advice, "deduplicated": False}), 201


@app.post("/api/matches/<match_id>/finish")
@require_api_key
def finish_match(match_id: str):
    final_score = _text(_json(), "final_score", max_length=120)
    match = db.finish_match(match_id, final_score)
    if not match:
        raise APIError("Матч не найден или уже завершён", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.delete("/api/matches/<match_id>")
@require_api_key
def cancel_match(match_id: str):
    match = db.cancel_match(match_id)
    if not match:
        raise APIError("Матч не найден или уже завершён", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.get("/api/matches")
@require_api_key
def list_matches():
    return jsonify({"matches": db.list_matches()})


@app.get("/api/matches/<match_id>")
@require_api_key
def match_detail(match_id: str):
    return jsonify(_bundle_or_404(match_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
