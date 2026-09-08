"""Versioned Pult API; legacy routes remain intact in app.py."""
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL

from flask import jsonify, request

import db
import gpt

_api = None
DOSSIER_VERSION = 'pult-dossier-1'


def fail(message, code='bad_request', status=400):
    raise _api.APIError(message, status, code)


def outcome(score):
    tokens = str(score or '').strip().split()
    if not tokens:
        return None
    sets = [re.fullmatch(r'(\d+)\s*[-–—:]\s*(\d+)(?:\(\d+\))?[,;]?', token) for token in tokens]
    if not all(sets):
        return None
    pairs = [(int(s[1]), int(s[2])) for s in sets]
    if any(a == b for a, b in pairs):
        return None
    balance = sum(1 if a > b else -1 for a, b in pairs)
    return 'win' if balance > 0 else 'loss' if balance < 0 else None


def validate_final_score(score):
    value = _api._text({'final_score': score}, 'final_score', max_length=120)
    if not 1 <= len(value.split()) <= 5 or outcome(value) is None:
        fail('Проверь сеты: у каждого сета и матча должен быть победитель')
    return value


def statistics(matches, reviews):
    completed = [m for m in matches if m['status'] == 'completed']
    ids = {m['id'] for m in completed}
    outcomes = [outcome(m.get('final_score')) for m in completed]
    helpful = [r['app_helpful'] for r in reviews if r['match_id'] in ids and isinstance(r.get('app_helpful'), bool)]
    return dict(completed=len(completed), wins=outcomes.count('win'), losses=outcomes.count('loss'),
                unknown=outcomes.count(None), helpful_yes=helpful.count(True), helpful_total=len(helpful),
                helpful_percent=round(100 * helpful.count(True) / len(helpful)) if helpful else None)


def validate_observation(payload):
    event_type = _api._choice(payload, 'event_type', {'changeover', 'new_set'})
    own = _api._choices(payload, 'own_issues', _api.SELF_ISSUES)
    opp = _api._choices(payload, 'opponent_actions', _api.OPPONENT_ACTIONS)
    comment = _api._text(payload, 'comment', required=False)
    if not own and not opp and not comment:
        fail('Отметь хотя бы одно наблюдение или напиши комментарий')
    value = dict(event_type=event_type, own_issues=own, opponent_actions=opp, comment=comment,
                 score_state=None, set_stage=None, completed_set_result=None, energy_level=None)
    if event_type == 'new_set':
        value.update(completed_set_result=_api._choice(payload, 'completed_set_result', {'won', 'lost'}),
                     energy_level=_api._integer(payload, 'energy_level', 1, 5))
    else:
        value.update(score_state=_api._choice(payload, 'score_state', _api.SCORE_STATES),
                     set_stage=_api._choice(payload, 'set_stage', _api.SET_STAGES))
    return value


def validate_review(payload):
    value = {key: _api._text(payload, key, required=False, max_length=500) for key in (
        'own_errors', 'emotional_state', 'opponent_style_note', 'opponent_what_worked', 'opponent_errors')}
    if not any(value.values()):
        fail('Добавь хотя бы одно наблюдение словами')
    value.update(physical_rating=_api._integer(payload, 'physical_rating', 1, 5),
                 mental_rating=_api._integer(payload, 'mental_rating', 1, 5),
                 app_helpful=_api._boolean(payload, 'app_helpful'),
                 opponent_styles=_api._choices(payload, 'opponent_styles', _api.OPPONENT_STYLE_CHIPS))
    value['opponent_style'] = ' · '.join([*value['opponent_styles'], value['opponent_style_note']]).strip(' ·')
    value.update(technical_comment=value['own_errors'], mental_comment=value['emotional_state'], advice_changed_play=None)
    return value


def prep_input(payload):
    match = {key: _api._choice(payload, key, choices) for key, choices in (
        ('match_type', _api.MATCH_TYPES), ('surface', _api.SURFACES),
        ('session_type', _api.SESSION_TYPES), ('session_duration', _api.SESSION_DURATIONS))}
    for key, length, required in [('opponent_name', 100, False), ('opponent_level', 100, True),
                                  ('opponent_style', 200, False), ('weather', 200, False)]:
        match[key] = _api._text(payload, key, required=required, max_length=length)
    match['session_format'] = _api.LEGACY_SESSION_FORMATS.get((match['session_type'], match['session_duration']), 'friendly')
    survey = {key: _api._text(payload, key, required=key != 'last_meal', max_length=200 if key == 'last_meal' else 300)
              for key in ('last_meal', 'physical_state', 'mindset')}
    survey['energy_level'] = _api._integer(payload, 'energy_level', 1, 5)
    return match, survey


def source_hash(name, sources):
    return hashlib.sha256(json.dumps([DOSSIER_VERSION, name, sources], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def opponent_records(name):
    matches = [m for m in db.read_all('matches', {'opponent_name': name}) if m['status'] == 'completed']
    reviews = {r['match_id']: r for r in db.read_all('match_reviews')}
    records, sources = [], []
    for m in sorted(matches, key=lambda m: (m['match_date'], m['id']), reverse=True):
        r = reviews.get(m['id'])
        item = dict(match_id=m['id'], match_date=m['match_date'], final_score=m.get('final_score'), has_review=bool(r))
        for key in ('opponent_style', 'opponent_style_note', 'opponent_what_worked', 'opponent_errors'):
            item[key] = (r or {}).get(key) or ''
        item['opponent_styles'] = (r or {}).get('opponent_styles') or []
        records.append(item)
        if r and any(item[k] for k in ('opponent_style', 'opponent_style_note', 'opponent_styles', 'opponent_what_worked', 'opponent_errors')):
            sources.append(item)
    return matches, records, sources


def full_bundle(match_id):
    bundle = _api._bundle_or_404(match_id)
    bundle['events'] = sorted(db.read_all('match_events', {'match_id': match_id}), key=lambda r: (r['created_at'], r['id']))
    bundle['context_updates'] = sorted(db.read_all('match_context_updates', {'match_id': match_id}), key=lambda r: (r['created_at'], r['id']))
    return bundle


def generate_operation(kind, match_id, payload):
    if kind in ('prep_create', 'prep_update'):
        match, survey = prep_input(payload)
        revision = None
        if kind == 'prep_create':
            if db.get_active_match():
                fail('Сначала заверши или отмени активный матч', 'active_match_exists', 409)
        else:
            bundle = _api._bundle_or_404(match_id)
            revision = _api._integer(payload, 'revision', 1, 1000000)
            if bundle['match']['status'] != 'preparing' or bundle['prep'].get('revision', 1) != revision:
                fail('Подготовка уже изменилась или матч начат. Открой сохранённый план', 'revision_conflict', 409)
        profile = db.get_player_profile() or {}
        history = []
        if match['opponent_name']:
            _, _, sources = opponent_records(match['opponent_name'])
            cache = db.dossier_cache(match['opponent_name'])
            history = sources[:8]
            if cache and cache['source_hash'] == source_hash(match['opponent_name'], sources):
                history = [{'summary': cache['summary'], 'source_count': len(sources)}, *sources[:3]]
            elif len(sources) > 8:
                history.append({'history_limited': True, 'total_sources': len(sources)})
        brief = gpt.generate_prep_brief(match, survey, db.get_recent_reviews(), profile, history)
        prep = {**survey, 'player_profile_snapshot': profile,
                'generated_game_plan': {k: brief[k] for k in ('opponent_cue', 'tactics', 'body', 'reset', 'focus')},
                'generated_brief_technical': brief['technical'], 'generated_brief_mental': brief['mental']}
        return dict(match=match, prep=prep, revision=revision)
    bundle = _api._bundle_or_404(match_id)
    if kind == 'event':
        if bundle['match']['status'] != 'in_progress':
            fail('Матч не начат или уже завершён', 'invalid_match_state', 409)
        observation = validate_observation(payload)
        context_match = {**bundle['match']}
        context_match.pop('current_score', None)
        context = dict(match=context_match, prep=bundle['prep'], previous_events=bundle['events'][-12:])
        generator = gpt.generate_changeover_advice if observation['event_type'] == 'changeover' else gpt.generate_new_set_advice
        advice = generator(context, observation)
        return {**{k: v for k, v in observation.items() if k != 'comment'},
                'observation_comment': observation['comment'], 'generated_advice': advice}
    if kind == 'review':
        if bundle['match']['status'] not in ('completed', 'cancelled'):
            fail('Разбор доступен после завершения', 'invalid_match_state', 409)
        if bundle.get('review'):
            return bundle['review']  # Commit returns the existing review, without another model call.
        value = validate_review(payload)
        summary = gpt.generate_post_match_review(bundle['match'], bundle['prep'], value)
        return {**value, 'generated_technical_summary': summary['technical'], 'generated_mental_summary': summary['mental']}
    if kind == 'finish':
        return {'final_score': validate_final_score(payload.get('final_score'))}
    fail('Неизвестная операция')


def run_operation(kind, match_id, payload):
    key = _api._valid_uuid(payload.get('idempotency_key'), 'idempotency_key')
    body_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    claim = db.claim_operation(key, kind, match_id, body_hash)
    status = claim['status']
    if status == 'succeeded':
        return jsonify(claim['result'])
    if status == 'conflict':
        fail('Этот запрос уже использован для других данных', 'operation_conflict', 409)
    if status in ('pending', 'busy'):
        fail('Запрос ещё выполняется. Проверь результат или повтори позже', 'operation_pending', 409)
    token = claim['token']
    try:
        generated = generate_operation(kind, match_id, payload)
        return jsonify(db.commit_operation(key, token, generated))
    except Exception as error:
        code = getattr(error, 'code', 'operation_failed')
        try:
            db.fail_operation(key, token, {'code': code, 'message': str(error) if isinstance(error, _api.APIError) else 'Не удалось сохранить. Повтори запрос'})
        except Exception:
            _api.logger.exception('Could not mark operation failed')
        if isinstance(error, _api.APIError):
            raise
        for marker in ('revision_conflict', 'active_match_exists', 'invalid_match_state', 'operation_expired'):
            if marker in str(error):
                fail('Данные изменились. Открой сохранённый матч', marker, 409)
        _api.logger.exception('Pult operation failed')
        fail('Не удалось получить или сохранить ответ. Ввод сохранён — повтори запрос', 'operation_failed', 503)


def period_matches():
    month = request.args.get('month', '')
    if month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        fail('Некорректный месяц')
    return [m for m in db.read_all('matches') if m['status'] != 'cancelled' and (not month or m['match_date'].startswith(month))]


def page(items):
    try:
        offset = max(0, int(request.args.get('offset', 0)))
        limit = min(100, max(1, int(request.args.get('limit', 30))))
    except ValueError:
        fail('Некорректная страница')
    return items[offset:offset+limit], offset+limit if offset+limit < len(items) else None


def dossier(name):
    matches, records, sources = opponent_records(name)
    cache = db.dossier_cache(name)
    current_hash = source_hash(name, sources)
    rows, next_offset = page(records)
    return dict(opponent_name=name, stats=statistics(matches, []), records=rows, next_offset=next_offset,
                source_count=len(sources), summary=cache['summary'] if cache else None,
                updated_at=cache['updated_at'] if cache else None,
                stale=bool(sources) and (not cache or cache['source_hash'] != current_hash))


def refresh_dossier(payload):
    name = _api._text(payload, 'opponent_name', max_length=100)
    _, _, sources = opponent_records(name)
    if not sources:
        return jsonify({'summary': None})
    fingerprint = source_hash(name, sources)
    key = str(uuid5(NAMESPACE_URL, fingerprint))
    claim = db.claim_operation(key, 'dossier_refresh', None, fingerprint)
    if claim['status'] == 'succeeded':
        return jsonify(claim['result'])
    if claim['status'] != 'claimed':
        fail('Сводка обновляется. Попробуй позже', 'operation_pending', 409)
    try:
        def keep_lease():
            if not db.renew_operation(key, claim['token']):
                fail('Операция устарела. Обнови досье', 'operation_expired', 409)
        summary = gpt.generate_opponent_dossier(sources, progress=keep_lease)
        # Do not publish a summary labelled fresh if its inputs changed during generation.
        _, _, latest = opponent_records(name)
        if source_hash(name, latest) != fingerprint:
            fail('Появились новые наблюдения. Обнови досье', 'sources_changed', 409)
        return jsonify(db.commit_operation(key, claim['token'], dict(opponent_name=name, source_hash=fingerprint, summary=summary)))
    except Exception as error:
        db.fail_operation(key, claim['token'], {'code': 'summary_failed'})
        if isinstance(error, _api.APIError):
            raise
        _api.logger.exception('Dossier generation failed')
        fail('Сводка не обновилась. Исходные записи доступны ниже', 'summary_failed', 503)


def dispatch():
    path = request.path
    if path == '/api/matches/stats':
        return jsonify(statistics(period_matches(), db.read_all('match_reviews')))
    if path == '/api/opponents':
        query = request.args.get('query', '').strip().casefold()
        names = sorted({m['opponent_name'] for m in db.read_all('matches') if m.get('opponent_name') and query in m['opponent_name'].casefold()})
        items, nxt = page(names)
        return jsonify({'opponents': items, 'next_offset': nxt})
    if path == '/api/opponents/dossier':
        name = _api._text({'opponent_name': request.args.get('opponent_name')}, 'opponent_name', max_length=100)
        return jsonify(dossier(name))
    if path == '/api/opponents/dossier/refresh':
        return refresh_dossier(_api._json())
    if path.startswith('/api/operations/'):
        key = _api._valid_uuid(path.rsplit('/', 1)[1], 'idempotency_key')
        op = db.get_operation(key)
        if not op:
            return jsonify({'status': 'not_found'})
        status = op['status']
        if status == 'pending' and datetime.fromisoformat(op['lease_until'].replace('Z', '+00:00')) < datetime.now(timezone.utc):
            status = 'failed'  # Expired token cannot commit; retry safely reclaims it.
        return jsonify({'status': status, 'result': op.get('result'), 'error': op.get('error')})
    if request.method == 'GET':
        if path == '/api/matches':
            matches = sorted(period_matches(), key=lambda m: (m['match_date'], m['created_at'], m['id']), reverse=True)
            rows, nxt = page(matches)
            reviews = {r['match_id'] for r in db.read_all('match_reviews')}
            return jsonify({'matches': [{**m, 'has_review': m['id'] in reviews} for m in rows], 'next_offset': nxt})
        if path == '/api/matches/active':
            active = db.get_active_match()
            return jsonify({'active_match': full_bundle(active['id']) if active else None})
        return jsonify(full_bundle(path.rsplit('/', 1)[1]))
    payload = _api._json()
    if path == '/api/matches/prep':
        return run_operation('prep_create', None, payload)
    match_id, action = path.split('/')[-2:]
    if action == 'start':
        revision = _api._integer(payload, 'revision', 1, 1000000)
        try:
            return jsonify(db.start_match_v2(match_id, revision))
        except Exception:
            fail('Матч или план изменился. Перечитай данные', 'revision_conflict', 409)
    kind = {'prep': 'prep_update', 'events': 'event', 'finish': 'finish', 'review': 'review'}[action]
    return run_operation(kind, match_id, payload)


def install(api):
    global _api
    _api = api
    protected_dispatch = api.require_api_key(dispatch)
    # Register routes as well as dispatching versions so Flask can answer CORS OPTIONS.
    for index, (path, methods) in enumerate([
        ('/api/matches/stats', ['GET']), ('/api/opponents', ['GET']),
        ('/api/opponents/dossier', ['GET']), ('/api/opponents/dossier/refresh', ['POST']),
        ('/api/operations/<operation_id>', ['GET']), ('/api/matches/<match_id>/prep', ['PUT']),
    ]):
        api.app.add_url_rule(path, 'pult_' + str(index), lambda **kwargs: protected_dispatch(), methods=methods)

    @api.app.before_request
    def route_pult():
        if request.method == 'OPTIONS' or getattr(request.routing_exception, 'code', None) == 405:
            return None
        path = request.path
        special = path in ('/api/matches/stats', '/api/opponents', '/api/opponents/dossier', '/api/opponents/dossier/refresh') or path.startswith('/api/operations/')
        data = request.get_json(silent=True) or {}
        version = data.get('contract_version') if isinstance(data, dict) else None
        v2 = version == 2 or request.args.get('contract_version') == '2'
        eligible = (request.method == 'GET' and (path == '/api/matches' or re.fullmatch(r'/api/matches/[^/]+', path))) or (request.method in ('POST', 'PUT') and (path == '/api/matches/prep' or re.fullmatch(r'/api/matches/[^/]+/(prep|events|finish|review|start)', path)))
        if special or (v2 and eligible):
            return protected_dispatch()
        return None
