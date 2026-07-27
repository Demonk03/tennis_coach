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
