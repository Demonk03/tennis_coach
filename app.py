import hmac
import logging
import os
from functools import wraps
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import db
import gpt

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

SELF_ISSUES = {
    "many_errors",
    "overhitting",
    "short_balls",
    "slow_movement",
    "tight",
    "emotionally_drained",
}
OPPONENT_ACTIONS = {
    "slice",
    "drop_shots",
    "gets_everything_back",
    "baseline_pressure",
    "flat_hitting",
    "comes_to_net",
}
OPPONENT_STYLE_CHIPS = {
    "Силовая игра с задней линии",
    "Укороты и игра у сетки",
    "Защита, много подбирает",
    "Тяжёлый топспин",
    "Плоский быстрый удар",
    "Много слайсов",
}
MATCH_TYPES = {"singles", "doubles"}
SURFACES = {"hard", "clay", "grass", "carpet", "other"}
SESSION_FORMATS = {"tournament", "1h_session", "2h_session", "friendly"}
SCORE_KEYS = {"sets", "game", "serving"}
SCORE_STATES = {"ahead", "even", "behind"}
SET_STAGES = {"early", "middle", "late"}
OPPONENT_HISTORY_MIN_MATCHES = 1


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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
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


def _boolean(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise APIError(f"Поле {field} должно быть true или false")
    return value


def _choices(payload: dict[str, Any], field: str, allowed: set[str]) -> list[str]:
    values = payload.get(field, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise APIError(f"Поле {field} должно быть списком")
    if len(values) != len(set(values)) or not set(values).issubset(allowed):
        raise APIError(f"Недопустимое значение поля {field}")
    return values


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


def _bundle_or_404(match_id: str) -> dict[str, Any]:
    bundle = db.get_match_bundle(match_id)
    if not bundle:
        raise APIError("Матч не найден", 404, "not_found")
    return bundle


def _is_unique_violation(error: Exception) -> bool:
    if str(getattr(error, "code", "")) == "23505":
        return True
    for arg in getattr(error, "args", ()):
        if isinstance(arg, dict) and str(arg.get("code", "")) == "23505":
            return True
    return '"code":"23505"' in str(error).replace(" ", "")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/profile")
@require_api_key
def get_profile():
    return jsonify({"profile": db.get_player_profile()})


@app.put("/api/profile")
@require_api_key
def save_profile():
    payload = _json()
    profile = {
        "level": _text(payload, "level", required=False, max_length=100),
        "experience": _text(payload, "experience", required=False, max_length=200),
        "playing_style": _text(payload, "playing_style", required=False, max_length=500),
        "strengths": _text(payload, "strengths", required=False, max_length=500),
        "medical_context": _text(payload, "medical_context", required=False, max_length=1000),
        "mental_pattern": _text(payload, "mental_pattern", required=False, max_length=500),
    }
    return jsonify({"profile": db.save_player_profile(profile)})


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
    player_profile = db.get_player_profile()
    past_reviews = db.get_recent_reviews(limit=3)
    opponent_history = (
        db.get_opponent_history(match_data["opponent_name"], limit=5)
        if match_data["opponent_name"]
        else []
    )
    try:
        brief = gpt.generate_prep_brief(
            match_data, survey, past_reviews, player_profile, opponent_history
        )
    except Exception as error:
        logger.exception("Prep advice generation failed")
        raise APIError("Не удалось получить бриф. Попробуйте ещё раз", 503, "ai_unavailable") from error

    match = db.create_match({**match_data, "status": "preparing"})
    try:
        game_plan = {
            key: brief[key]
            for key in ("opponent_cue", "tactics", "body", "reset", "focus")
        }
        prep = db.save_prep({
            "match_id": match["id"],
            "player_profile_snapshot": player_profile or {},
            **survey,
            "generated_brief_technical": brief["technical"],
            "generated_brief_mental": brief["mental"],
            "generated_game_plan": game_plan,
        })
    except Exception:
        db.cancel_match(match["id"])
        raise

    return jsonify({
        "match": match,
        "prep": prep,
        "brief": brief,
        "opponent_history": opponent_history,
    }), 201


@app.get("/api/opponents/history")
@require_api_key
def opponent_history():
    opponent_name = _text(
        {"opponent_name": request.args.get("opponent_name")},
        "opponent_name",
        max_length=100,
    )
    history = db.get_opponent_history(opponent_name, limit=5)
    useful = [
        item for item in history
        if item.get("opponent_style")
        or item.get("opponent_what_worked")
        or item.get("opponent_errors")
    ]
    card = None
    if len(useful) >= OPPONENT_HISTORY_MIN_MATCHES:
        card = {
            "opponent_name": opponent_name,
            "match_count": len(useful),
            "style": next((item.get("opponent_style") for item in useful if item.get("opponent_style")), ""),
            "what_worked": next((item.get("opponent_what_worked") for item in useful if item.get("opponent_what_worked")), ""),
            "errors": next((item.get("opponent_errors") for item in useful if item.get("opponent_errors")), ""),
        }
    return jsonify({
        "card": card,
        "history": history,
        "minimum_matches": OPPONENT_HISTORY_MIN_MATCHES,
    })


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


@app.patch("/api/matches/<match_id>/opponent-style")
@require_api_key
def update_opponent_style(match_id: str):
    payload = _json()
    opponent_style = _choice(payload, "opponent_style", OPPONENT_STYLE_CHIPS)
    match = db.update_opponent_style(match_id, opponent_style)
    if not match:
        raise APIError("Стиль соперника можно уточнить только в активном матче", 409, "invalid_match_state")
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
    own_issues = _choices(payload, "own_issues", SELF_ISSUES)
    opponent_actions = _choices(payload, "opponent_actions", OPPONENT_ACTIONS)
    comment = _text(payload, "comment", required=False, max_length=300)
    if not own_issues and not opponent_actions and not comment:
        raise APIError("Отметьте хотя бы одно наблюдение")

    observation = {
        "event_type": event_type,
        "own_issues": own_issues,
        "opponent_actions": opponent_actions,
        "comment": comment,
        "score_state": _choice(payload, "score_state", SCORE_STATES),
        "set_stage": _choice(payload, "set_stage", SET_STAGES),
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
        "working_well": [],
        "not_working": [],
        "how_feeling": comment,
        "energy_level": energy_level,
        "score_at_event": bundle["match"].get("current_score") or {},
        "own_issues": own_issues,
        "opponent_actions": opponent_actions,
        "observation_comment": comment,
        "score_state": observation["score_state"],
        "set_stage": observation["set_stage"],
        "generated_advice": advice,
    })
    return jsonify({"event": event, "advice": advice, "deduplicated": False}), 201


@app.post("/api/matches/<match_id>/finish")
@require_api_key
def finish_match(match_id: str):
    final_score = _text(_json(), "final_score", max_length=120)
    match = db.finish_match(match_id, final_score)
    if not match:
        raise APIError("Матч не найден или уже завершён", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.post("/api/matches/<match_id>/review")
@require_api_key
def create_review(match_id: str):
    bundle = _bundle_or_404(match_id)
    if bundle["match"]["status"] not in {"completed", "cancelled"}:
        raise APIError("Разбор доступен только после завершения матча", 409, "invalid_match_state")

    payload = _json()
    review_input = {
        "physical_rating": _integer(payload, "physical_rating", 1, 5),
        "mental_rating": _integer(payload, "mental_rating", 1, 5),
        "own_errors": _text(payload, "own_errors", max_length=500),
        "emotional_state": _text(payload, "emotional_state", max_length=500),
        "opponent_style": _text(payload, "opponent_style", required=False, max_length=200),
        "opponent_what_worked": _text(payload, "opponent_what_worked", max_length=500),
        "opponent_errors": _text(payload, "opponent_errors", max_length=500),
        "advice_changed_play": _boolean(payload, "advice_changed_play"),
    }
    try:
        summary = gpt.generate_post_match_review(
            bundle["match"], bundle["prep"], review_input
        )
    except Exception as error:
        logger.exception("Post-match review generation failed")
        raise APIError(
            "Не удалось получить разбор. Попробуйте ещё раз", 503, "ai_unavailable"
        ) from error

    try:
        review = db.save_review({
            "match_id": match_id,
            **review_input,
            # Keep legacy columns populated while older records and clients coexist.
            "technical_comment": review_input["own_errors"],
            "mental_comment": review_input["emotional_state"],
            "generated_technical_summary": summary["technical"],
            "generated_mental_summary": summary["mental"],
        })
    except Exception as error:
        if _is_unique_violation(error):
            raise APIError(
                "Этот матч уже разобран", 409, "review_already_exists"
            ) from error
        raise

    return jsonify({"review": review, "summary": summary}), 201


@app.delete("/api/matches/<match_id>")
@require_api_key
def cancel_match(match_id: str):
    match = db.cancel_match(match_id)
    if not match:
        raise APIError("Матч не найден или уже завершён", 409, "invalid_match_state")
    return jsonify({"match": match})


@app.delete("/api/matches/<match_id>/permanent")
@require_api_key
def delete_completed_match(match_id: str):
    match = db.delete_completed_match(match_id)
    if not match:
        raise APIError(
            "Удалить можно только завершённый матч", 409, "invalid_match_state"
        )
    return jsonify({"deleted_match": match})


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
