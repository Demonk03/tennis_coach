from types import SimpleNamespace

import gpt


def _mock_client(mocker, content: str):
    client = mocker.MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    mocker.patch("gpt._get_client", return_value=client)
    return client


def test_prep_brief_sends_structured_context(mocker):
    client = _mock_client(mocker, "Играй глубоко и сохраняй спокойный ритм.")

    result = gpt.generate_prep_brief(
        {"surface": "hard", "opponent_level": "equal"},
        {"energy_level": 3, "physical_state": "нормально"},
        {"readiness": 78, "average_hrv": 46},
    )

    assert "Играй глубоко" in result
    call = client.chat.completions.create.call_args.kwargs
    assert call["messages"][0]["role"] == "system"
    assert '"readiness": 78' in call["messages"][1]["content"]


def test_changeover_advice_is_hard_limited(mocker):
    _mock_client(mocker, "слово " * 200)

    result = gpt.generate_changeover_advice({"match": {}}, {"score": {"game": "30-30"}})

    assert len(result) <= 321
    assert result.endswith("…")


def test_empty_openai_response_fails(mocker):
    _mock_client(mocker, "   ")

    try:
        gpt.generate_new_set_advice({}, {})
    except RuntimeError as error:
        assert "empty" in str(error)
    else:
        raise AssertionError("Expected RuntimeError")
