import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def get_client():
    """Create the Supabase client lazily so unit tests do not need the SDK."""
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
    return create_client(url, key)


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


def get_opponent_history(opponent_name: str, limit: int = 5) -> list[dict[str, Any]]:
    matches_response = (
        get_client()
        .table("matches")
        .select("id,match_date,opponent_name,opponent_style,final_score")
        .eq("opponent_name", opponent_name.strip())
        .eq("status", "completed")
        .order("match_date", desc=True)
        .limit(limit)
        .execute()
    )
    matches = matches_response.data
    if not matches:
        return []

    reviews_response = (
        get_client()
        .table("match_reviews")
        .select(
            "match_id,opponent_style,opponent_what_worked,opponent_errors,created_at"
        )
        .in_("match_id", [match["id"] for match in matches])
        .execute()
    )
    reviews_by_match = {review["match_id"]: review for review in reviews_response.data}
    history = []
    for match in matches:
        review = reviews_by_match.get(match["id"])
        if not review:
            continue
        history.append({
            **match,
            **review,
            "opponent_style": review.get("opponent_style") or match.get("opponent_style") or "",
        })
    return history


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
    return update_style_v2(match_id, opponent_style)


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


# Pult v2: paginated reads avoid Supabase's default response cap.
def read_all(table: str, filters: dict | None = None) -> list[dict]:
    result = []
    offset = 0
    while True:
        query = get_client().table(table).select('*').order('id' if table != 'opponent_dossiers' else 'opponent_name')
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        page = query.range(offset, offset + 499).execute().data
        result.extend(page)
        if len(page) < 500:
            return result
        offset += 500


def claim_operation(key, kind, match_id, body_hash):
    return get_client().rpc('pult_claim_operation', {
        'p_id': key, 'p_kind': kind, 'p_match_id': match_id, 'p_hash': body_hash,
    }).execute().data


def commit_operation(key, token, payload):
    return get_client().rpc('pult_commit_operation', {
        'p_id': key, 'p_token': token, 'p_payload': payload,
    }).execute().data


def fail_operation(key, token, error):
    get_client().rpc('pult_fail_operation', {'p_id': key, 'p_token': token, 'p_error': error}).execute()


def get_operation(key):
    data = get_client().table('pult_operations').select('*').eq('id', key).limit(1).execute().data
    return data[0] if data else None


def start_match_v2(match_id, revision=None):
    return get_client().rpc('pult_start_match', {'p_match_id': match_id, 'p_revision': revision}).execute().data


def update_style_v2(match_id, style):
    return get_client().rpc('pult_update_style', {'p_match_id': match_id, 'p_style': style}).execute().data


def dossier_cache(name):
    rows = get_client().table('opponent_dossiers').select('*').eq('opponent_name', name).limit(1).execute().data
    return rows[0] if rows else None


def renew_operation(key, token):
    return get_client().rpc('pult_renew_operation', {'p_id': key, 'p_token': token}).execute().data
