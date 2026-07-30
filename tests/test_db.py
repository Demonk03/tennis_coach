from types import SimpleNamespace

import db


def test_get_latest_oura_log_uses_configured_user(mocker):
    client = mocker.MagicMock()
    client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "log-1", "user_id": "user-1", "readiness_score": 81}]
    )
    mocker.patch("db.get_client", return_value=client)

    result = db.get_latest_oura_log("user-1")

    assert result["readiness_score"] == 81
    client.table.assert_called_once_with("health_logs")
    client.table.return_value.select.return_value.eq.assert_called_once_with("user_id", "user-1")


def test_create_match_returns_inserted_row(mocker):
    client = mocker.MagicMock()
    client.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "match-1"}])
    mocker.patch("db.get_client", return_value=client)

    result = db.create_match({"match_type": "singles"})

    assert result == {"id": "match-1"}
    client.table.assert_called_once_with("matches")


def test_get_match_bundle_returns_none_for_missing_match(mocker):
    mocker.patch("db.get_match", return_value=None)

    assert db.get_match_bundle("missing") is None


def test_get_match_bundle_includes_review(mocker):
    mocker.patch("db.get_match", return_value={"id": "match-1", "status": "completed"})
    mocker.patch("db.get_prep_for_match", return_value={"id": "prep-1"})
    mocker.patch("db.get_events_for_match", return_value=[])
    mocker.patch("db.get_review_for_match", return_value={"id": "review-1"})

    result = db.get_match_bundle("match-1")

    assert result["review"]["id"] == "review-1"


def test_get_recent_reviews_uses_requested_limit(mocker):
    client = mocker.MagicMock()
    query = client.table.return_value.select.return_value.order.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[{"id": "review-1"}])
    mocker.patch("db.get_client", return_value=client)

    result = db.get_recent_reviews(limit=3)

    assert result == [{"id": "review-1"}]
    client.table.assert_called_once_with("match_reviews")
    client.table.return_value.select.return_value.order.return_value.limit.assert_called_once_with(3)


def test_list_matches_still_excludes_cancelled(mocker):
    client = mocker.MagicMock()
    query = (
        client.table.return_value.select.return_value.neq.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[])
    mocker.patch("db.get_client", return_value=client)

    db.list_matches()

    client.table.return_value.select.return_value.neq.assert_called_once_with("status", "cancelled")
