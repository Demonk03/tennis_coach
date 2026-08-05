import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()


OURA_FIELDS = (
    "id,user_id,date,readiness_score,sleep_score,average_hrv,"
    "average_heart_rate,total_sleep_duration,activity_score"
)


def get_client():
    """Create the Supabase client lazily so unit tests do not need the SDK."""
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
    return create_client(url, key)


def get_latest_oura_log(user_id: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("health_logs")
        .select(OURA_FIELDS)
        .eq("user_id", user_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_player_profile() -> dict[str, Any] | None:
    response = (
        get_client()
        .table("player_profile")
        .select("*")
        .eq("id", True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def save_player_profile(payload: dict[str, Any]) -> dict[str, Any]:
    response = (
        get_client()
        .table("player_profile")
        .upsert({"id": True, **payload}, on_conflict="id")
        .execute()
    )
    return response.data[0]


def get_active_match() -> dict[str, Any] | None:
    response = (
        get_client()
        .table("matches")
        .select("*")
        .in_("status", ["preparing", "in_progress"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def create_match(payload: dict[str, Any]) -> dict[str, Any]:
    response = get_client().table("matches").insert(payload).execute()
    return response.data[0]


def save_prep(payload: dict[str, Any]) -> dict[str, Any]:
    response = get_client().table("match_prep").insert(payload).execute()
    return response.data[0]


def save_review(payload: dict[str, Any]) -> dict[str, Any]:
    response = get_client().table("match_reviews").insert(payload).execute()
    return response.data[0]


def get_match(match_id: str) -> dict[str, Any] | None:
    response = get_client().table("matches").select("*").eq("id", match_id).limit(1).execute()
    return response.data[0] if response.data else None


def get_prep_for_match(match_id: str) -> dict[str, Any] | None:
    response = (
        get_client().table("match_prep").select("*").eq("match_id", match_id).limit(1).execute()
    )
    return response.data[0] if response.data else None


def get_events_for_match(match_id: str) -> list[dict[str, Any]]:
    response = (
        get_client()
        .table("match_events")
        .select("*")
        .eq("match_id", match_id)
        .order("created_at")
        .execute()
    )
    return response.data


def get_review_for_match(match_id: str) -> dict[str, Any] | None:
    response = (
        get_client().table("match_reviews").select("*").eq("match_id", match_id).limit(1).execute()
    )
    return response.data[0] if response.data else None


def get_recent_reviews(limit: int = 3) -> list[dict[str, Any]]:
    response = (
        get_client()
        .table("match_reviews")
        .select(
            "match_id,physical_rating,mental_rating,technical_comment,mental_comment,"
            "generated_technical_summary,generated_mental_summary,created_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def get_match_bundle(match_id: str) -> dict[str, Any] | None:
    match = get_match(match_id)
    if not match:
        return None
    return {
        "match": match,
        "prep": get_prep_for_match(match_id),
        "events": get_events_for_match(match_id),
        "review": get_review_for_match(match_id),
    }


def start_match(match_id: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("matches")
        .update({"status": "in_progress"})
        .eq("id", match_id)
        .eq("status", "preparing")
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def update_score(match_id: str, score: dict[str, str]) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("matches")
        .update({"current_score": score})
        .eq("id", match_id)
        .eq("status", "in_progress")
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def update_opponent_style(match_id: str, opponent_style: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("matches")
        .update({"opponent_style": opponent_style})
        .eq("id", match_id)
        .eq("status", "in_progress")
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def finish_match(match_id: str, final_score: str) -> dict[str, Any] | None:
    completed_at = datetime.now(timezone.utc).isoformat()
    response = (
        get_client()
        .table("matches")
        .update({"status": "completed", "final_score": final_score, "completed_at": completed_at})
        .eq("id", match_id)
        .in_("status", ["preparing", "in_progress"])
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def cancel_match(match_id: str) -> dict[str, Any] | None:
    completed_at = datetime.now(timezone.utc).isoformat()
    response = (
        get_client()
        .table("matches")
        .update({"status": "cancelled", "completed_at": completed_at})
        .eq("id", match_id)
        .in_("status", ["preparing", "in_progress"])
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def delete_completed_match(match_id: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("matches")
        .delete()
        .eq("id", match_id)
        .in_("status", ["completed", "cancelled"])
        .execute()
    )
    return response.data[0] if response.data else None


def get_event_by_idempotency_key(key: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("match_events")
        .select("*")
        .eq("idempotency_key", key)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def add_event(payload: dict[str, Any]) -> dict[str, Any]:
    response = get_client().table("match_events").insert(payload).execute()
    return response.data[0]


def list_matches(limit: int = 50) -> list[dict[str, Any]]:
    response = (
        get_client()
        .table("matches")
        .select("*")
        .neq("status", "cancelled")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data
