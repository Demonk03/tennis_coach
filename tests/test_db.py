from types import SimpleNamespace

import db


def test_create_match_returns_inserted_row(mocker):
    client = mocker.MagicMock()
    client.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(data=[{"id": "match-1"}])
    mocker.patch("db.get_client", return_value=client)

    result = db.create_match({"match_type": "singles"})

    assert result == {"id": "match-1"}
    client.table.assert_called_once_with("matches")


def test_get_player_profile_returns_singleton(mocker):
    client = mocker.MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[{"id": True, "level": "3.5"}])
    mocker.patch("db.get_client", return_value=client)

    result = db.get_player_profile()

    assert result["level"] == "3.5"
    client.table.assert_called_once_with("player_profile")
    client.table.return_value.select.return_value.eq.assert_called_once_with("id", True)


def test_save_player_profile_upserts_singleton(mocker):
    client = mocker.MagicMock()
    client.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": True, "level": "3.5"}]
    )
    mocker.patch("db.get_client", return_value=client)

    result = db.save_player_profile({"level": "3.5"})

    assert result["id"] is True
    client.table.return_value.upsert.assert_called_once_with(
        {"id": True, "level": "3.5"}, on_conflict="id"
    )


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


def test_get_opponent_history_joins_completed_matches_with_reviews(mocker):
    client = mocker.MagicMock()
    matches_table = mocker.MagicMock()
    matches_query = (
        matches_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
    )
    matches_query.execute.return_value = SimpleNamespace(data=[{
        "id": "match-1",
        "opponent_name": "Андрей",
        "opponent_style": "Много слайсов",
    }])
    reviews_table = mocker.MagicMock()
    reviews_table.select.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=[{
        "match_id": "match-1",
        "opponent_style": "",
        "opponent_what_worked": "Играть глубоко",
        "opponent_errors": "Ошибается по длине",
    }])
    client.table.side_effect = lambda name: {
        "matches": matches_table,
        "match_reviews": reviews_table,
    }[name]
    mocker.patch("db.get_client", return_value=client)

    result = db.get_opponent_history("Андрей", limit=5)

    assert result[0]["opponent_what_worked"] == "Играть глубоко"
    assert result[0]["opponent_style"] == "Много слайсов"
    matches_table.select.return_value.eq.assert_called_once_with("opponent_name", "Андрей")
    reviews_table.select.return_value.in_.assert_called_once_with("match_id", ["match-1"])


def test_list_matches_still_excludes_cancelled(mocker):
    client = mocker.MagicMock()
    query = (
        client.table.return_value.select.return_value.neq.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[])
    mocker.patch("db.get_client", return_value=client)

    db.list_matches()

    client.table.return_value.select.return_value.neq.assert_called_once_with("status", "cancelled")


def test_delete_completed_match_is_limited_to_terminal_statuses(mocker):
    client = mocker.MagicMock()
    query = client.table.return_value.delete.return_value.eq.return_value.in_.return_value
    query.execute.return_value = SimpleNamespace(data=[{"id": "match-1", "status": "completed"}])
    mocker.patch("db.get_client", return_value=client)

    result = db.delete_completed_match("match-1")

    assert result["id"] == "match-1"
    client.table.return_value.delete.return_value.eq.assert_called_once_with("id", "match-1")
    client.table.return_value.delete.return_value.eq.return_value.in_.assert_called_once_with(
        "status", ["completed", "cancelled"]
    )
