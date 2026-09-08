from uuid import uuid4

import pytest

import app as legacy
import pult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('API_KEY', 'test-key')
    return legacy.app.test_client()


AUTH = {'Authorization': 'Bearer test-key'}


def test_stats_do_not_mix_old_benefit_question():
    matches = [{'id': str(i), 'status': 'completed', 'final_score': '6-4 6-3'} for i in range(65)]
    matches += [{'id': 'unknown', 'status': 'completed', 'final_score': '?'},
                {'id': 'active', 'status': 'in_progress', 'final_score': None}]
    reviews = [{'match_id': '0', 'advice_changed_play': True},
               {'match_id': '1', 'app_helpful': True}, {'match_id': '2', 'app_helpful': False}]
    assert pult.statistics(matches, reviews) == {
        'completed': 66, 'wins': 65, 'losses': 0, 'unknown': 1,
        'helpful_yes': 1, 'helpful_total': 2, 'helpful_percent': 50,
    }


def test_new_set_describes_finished_set_without_fake_stage():
    value = pult.validate_observation({'event_type': 'new_set', 'own_issues': ['short_balls'],
        'opponent_actions': [], 'completed_set_result': 'lost', 'energy_level': 2})
    assert value['completed_set_result'] == 'lost'
    assert value['score_state'] is None and value['set_stage'] is None


def test_review_requires_one_text_but_not_four():
    value = pult.validate_review({'physical_rating': 3, 'mental_rating': 2, 'app_helpful': False,
        'own_errors': 'Ошибался', 'opponent_styles': ['Много слайсов', 'Тяжёлый топспин']})
    assert value['emotional_state'] == ''
    assert value['app_helpful'] is False
    assert value['advice_changed_play'] is None
    with pytest.raises(legacy.APIError):
        pult.validate_review({'physical_rating': 3, 'mental_rating': 2, 'app_helpful': True,
                             'opponent_styles': ['Много слайсов']})


def test_final_score_accepts_bagel_and_rejects_equal_sets():
    assert pult.validate_final_score('6-0 6-4') == '6-0 6-4'
    for score in ('0-0', '6-4 3-3', '6-4 4-6', 'garbage'):
        with pytest.raises(legacy.APIError):
            pult.validate_final_score(score)


def test_unknown_legacy_score_is_not_inferred_from_partial_parse():
    assert pult.outcome('6-4 abandoned') is None
    assert pult.outcome('7-6(5) 6-0') == 'win'


def test_operation_replay_does_not_call_generator(client, mocker):
    mocker.patch('pult.db.claim_operation', return_value={'status': 'succeeded', 'result': {'advice': 'same'}})
    generate = mocker.patch('pult.generate_operation')
    response = client.post('/api/matches/abc/events', headers=AUTH, json={
        'contract_version': 2, 'idempotency_key': str(uuid4())})
    assert response.status_code == 200
    assert response.json['advice'] == 'same'
    generate.assert_not_called()


def test_new_routes_require_auth(client):
    assert client.get('/api/matches/stats').status_code == 401


def test_dossier_hash_covers_all_sources_and_keeps_logins_separate():
    rows = [{'match_id': str(i), 'opponent_errors': 'Ошибки', 'match_date': '2026-09-01'} for i in range(9)]
    before = pult.source_hash('andrey', rows)
    rows[0]['opponent_errors'] = 'Изменено'
    assert pult.source_hash('andrey', rows) != before
    assert pult.source_hash('Андрей', rows) != pult.source_hash('andrey', rows)


def test_late_started_match_cannot_generate_updated_prep(mocker):
    from test_app import valid_prep_payload
    mocker.patch('pult._api._bundle_or_404', return_value={'match': {'status': 'in_progress'}, 'prep': {'revision': 1}})
    generate = mocker.patch('pult.gpt.generate_prep_brief')
    with pytest.raises(legacy.APIError, match='Подготовка'):
        pult.generate_operation('prep_update', str(uuid4()), {**valid_prep_payload(), 'revision': 1})
    generate.assert_not_called()


def test_existing_review_does_not_generate_again(mocker):
    review = {'id': 'review'}
    mocker.patch('pult._api._bundle_or_404', return_value={'match': {'status': 'completed'}, 'review': review})
    generate = mocker.patch('pult.gpt.generate_post_match_review')
    assert pult.generate_operation('review', 'match', {}) == review
    generate.assert_not_called()


def test_new_event_does_not_feed_stale_score_to_model(mocker):
    from test_app import active_bundle
    bundle = active_bundle()
    mocker.patch('pult._api._bundle_or_404', return_value=bundle)
    generate = mocker.patch('pult.gpt.generate_changeover_advice', return_value='Совет')
    pult.generate_operation('event', 'match', {'event_type': 'changeover', 'own_issues': ['short_balls'],
        'score_state': 'behind', 'set_stage': 'late'})
    assert 'current_score' not in generate.call_args.args[0]['match']
    assert 'current_score' in bundle['match']


def test_operation_key_with_changed_body_conflicts(client, mocker):
    mocker.patch('pult.db.claim_operation', return_value={'status': 'conflict'})
    generate = mocker.patch('pult.generate_operation')
    response = client.post('/api/matches/prep', headers=AUTH, json={'contract_version': 2, 'idempotency_key': str(uuid4())})
    assert response.status_code == 409
    generate.assert_not_called()


def test_dossier_does_not_join_aliases(mocker):
    def rows(table, filters=None):
        if table == 'matches':
            assert filters == {'opponent_name': 'andrey_k'}
            return [{'id': 'one', 'match_date': '2026-09-08', 'status': 'completed', 'final_score': '6-0'}]
        return [{'match_id': 'one', 'opponent_errors': 'Поздно подходит'},
                {'match_id': 'different-login', 'opponent_errors': 'НЕ ДОЛЖНО ПОПАСТЬ'}]
    mocker.patch('pult.db.read_all', side_effect=rows)
    _, records, sources = pult.opponent_records('andrey_k')
    assert len(records) == len(sources) == 1
    assert sources[0]['match_id'] == 'one'


def test_dossier_rejects_foreign_source_ids(mocker):
    from types import SimpleNamespace
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"style":{"text":"test","match_ids":["foreign"]},"what_worked":{"text":"Нет наблюдений","match_ids":[]},"errors":{"text":"Нет наблюдений","match_ids":[]}}'))])
    mocker.patch('gpt._get_client').return_value.chat.completions.create.return_value = response
    with pytest.raises(RuntimeError, match='sources'):
        pult.gpt.generate_opponent_dossier([{'match_id': 'allowed', 'match_date': '2026-09-08'}])


def test_new_endpoints_answer_browser_preflight(client):
    for path in ('/api/opponents', '/api/opponents/dossier', '/api/opponents/dossier/refresh',
                 '/api/operations/00000000-0000-0000-0000-000000000000',
                 '/api/matches/00000000-0000-0000-0000-000000000000/prep'):
        response = client.options(path, headers={'Origin': 'http://localhost:8000', 'Access-Control-Request-Method': 'PUT'})
        assert response.status_code < 300, path


def test_dossier_processes_every_source_and_renews_long_operation(mocker):
    import json
    from types import SimpleNamespace
    batches = []
    def respond(**kwargs):
        records = json.loads(kwargs['messages'][1]['content'].split('\n', 1)[1])
        batches.append(records)
        ids = [r['match_id'] for r in records] if 'match_id' in records[0] else [i for r in records for i in r['summary']['style']['match_ids']]
        value = {key: {'text': 'Наблюдения', 'match_ids': ids} for key in ('style', 'what_worked', 'errors')}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))])
    mocker.patch('gpt._get_client').return_value.chat.completions.create.side_effect = respond
    from unittest.mock import Mock
    progress = Mock()
    sources = [{'match_id': str(i), 'match_date': '2026-09-08'} for i in range(31)]
    result = pult.gpt.generate_opponent_dossier(sources, progress=progress)
    assert [r['match_id'] for batch in batches[:-1] for r in batch] == [r['match_id'] for r in sources]
    assert set(result['style']['match_ids']) == {r['match_id'] for r in sources}
    assert progress.call_count == len(batches) == 4
