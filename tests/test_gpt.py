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
        [{"generated_technical_summary": "Не торопиться на приёме"}],
    )

    assert "Играй глубоко" in result["technical"]
    assert "Играй глубоко" in result["mental"]
    assert client.chat.completions.create.call_count == 2
    calls = client.chat.completions.create.call_args_list
    assert calls[0].kwargs["messages"][0]["content"] == gpt.COACH_PROMPT
    assert calls[1].kwargs["messages"][0]["content"] == gpt.PSYCHOLOGIST_PROMPT
    assert '"readiness": 78' in calls[0].kwargs["messages"][1]["content"]
    assert "Не торопиться на приёме" in calls[1].kwargs["messages"][1]["content"]


def test_prep_brief_failure_in_second_voice_fails_whole_operation(mocker):
    complete = mocker.patch("gpt._complete", side_effect=["План тренера", RuntimeError("AI down")])

    try:
        gpt.generate_prep_brief({}, {}, None, [])
    except RuntimeError as error:
        assert "AI down" in str(error)
    else:
        raise AssertionError("Expected RuntimeError")

    assert complete.call_count == 2


def test_post_match_review_uses_two_voices_and_allows_missing_prep(mocker):
    complete = mocker.patch("gpt._complete", side_effect=["Вывод тренера", "Вывод психолога"])

    result = gpt.generate_post_match_review(
        {"id": "match-1", "status": "completed"},
        None,
        {
            "physical_rating": 4,
            "mental_rating": 2,
            "technical_comment": "Подача не шла",
            "mental_comment": "Терял фокус после ошибок",
        },
    )

    assert result == {"technical": "Вывод тренера", "mental": "Вывод психолога"}
    assert complete.call_count == 2
    assert complete.call_args_list[0].args[1]["prep"] is None
    assert complete.call_args_list[1].kwargs["system_prompt"] == gpt.PSYCHOLOGIST_PROMPT


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
