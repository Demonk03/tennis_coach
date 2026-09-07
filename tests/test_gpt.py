import json
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
    client = _mock_client(mocker, json.dumps({
        "opponent_cue": "Соперник любит контратаковать.",
        "tactics": [
            "Играй глубоко с запасом над сеткой.",
            "Не открывай угол без удобного мяча.",
            "После удара возвращайся в нейтральную позицию.",
        ],
        "body": "Проведи полную разминку и начни без форсирования.",
        "reset": "Отвернись от корта → длинный выдох → назови цель следующего мяча.",
        "focus": "Глубина, ноги, следующий мяч",
    }, ensure_ascii=False))

    result = gpt.generate_prep_brief(
        {"surface": "hard", "opponent_level": "equal"},
        {"energy_level": 3, "physical_state": "нормально"},
        [{"generated_technical_summary": "Не торопиться на приёме"}],
        {"level": "клубный 3.5", "playing_style": "контратакующий"},
        [{"opponent_what_worked": "Глубоко под бэкхэнд"}],
    )

    assert result["tactics"][0].startswith("Играй глубоко")
    assert result["technical"].startswith("Соперник любит")
    assert "Отвернись" in result["mental"]
    assert client.chat.completions.create.call_count == 1
    call = client.chat.completions.create.call_args
    assert call.kwargs["messages"][0]["content"] == gpt.MATCH_PLAN_PROMPT
    response_format = call.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["properties"]["tactics"]["minItems"] == 3
    assert response_format["json_schema"]["schema"]["properties"]["tactics"]["maxItems"] == 3
    assert "Не торопиться на приёме" in call.kwargs["messages"][1]["content"]
    assert "клубный 3.5" in call.kwargs["messages"][1]["content"]
    assert "Глубоко под бэкхэнд" in call.kwargs["messages"][1]["content"]


def test_prep_brief_rejects_plan_without_three_tactics(mocker):
    complete = mocker.patch("gpt._complete_json", return_value={
        "opponent_cue": "Соперник играет быстро.",
        "tactics": ["Играй глубоко."],
        "body": "Разомнись.",
        "reset": "Отвернись → выдохни → выбери цель.",
        "focus": "Следующий мяч",
    })

    try:
        gpt.generate_prep_brief({}, {}, [], None)
    except RuntimeError as error:
        assert "exactly three" in str(error)
    else:
        raise AssertionError("Expected RuntimeError")

    assert complete.call_count == 1


def test_prep_prompt_avoids_outcome_pressure_and_closed_eyes():
    assert "настрой на победу" in gpt.MATCH_PLAN_PROMPT
    assert "Не используй" in gpt.MATCH_PLAN_PROMPT
    assert "не предлагай закрывать глаза" in gpt.MATCH_PLAN_PROMPT


def test_prep_prompt_turns_low_state_into_lower_risk_tactics():
    assert "energy_level, physical_state и mindset" in gpt.MATCH_PLAN_PROMPT
    assert "понизить риск" in gpt.MATCH_PLAN_PROMPT
    assert "упростить первую подачу" in gpt.MATCH_PLAN_PROMPT
    assert "запасом над сеткой" in gpt.MATCH_PLAN_PROMPT
    assert "игровые решения, а не подбадривание" in gpt.MATCH_PLAN_PROMPT


def test_prompts_treat_profile_as_context_and_protect_medical_boundaries():
    assert "player_profile" in gpt.MATCH_PLAN_PROMPT
    assert "текущее состояние" in gpt.MATCH_PLAN_PROMPT
    assert "дозировки" in gpt.MATCH_PLAN_PROMPT
    assert "player_profile_snapshot" in gpt.COACH_PROMPT


def test_post_match_review_uses_two_voices_and_allows_missing_prep(mocker):
    complete = mocker.patch("gpt._complete", side_effect=["Вывод тренера", "Вывод психолога"])

    result = gpt.generate_post_match_review(
        {"id": "match-1", "status": "completed"},
        None,
        {
            "physical_rating": 4,
            "mental_rating": 2,
            "own_errors": "Подача не шла",
            "emotional_state": "Терял фокус после ошибок",
            "opponent_style": "Много слайсов",
            "opponent_what_worked": "Игра с запасом",
            "opponent_errors": "Ошибался на высоком мяче",
            "advice_changed_play": True,
        },
    )

    assert result == {"technical": "Вывод тренера", "mental": "Вывод психолога"}
    assert complete.call_count == 2
    assert complete.call_args_list[0].args[1]["prep"] is None
    assert complete.call_args_list[0].args[1]["review_input"]["opponent_errors"].startswith("Ошибался")
    assert complete.call_args_list[1].args[1]["review_input"]["advice_changed_play"] is True
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
