"""Three-day request boundaries; all model/retrieval calls here are mocked."""
from itertools import combinations
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.agenda import overlaps
from app.main import app
from app.smart_search import _call_times


@pytest.fixture(autouse=True)
def configured_model(monkeypatch):
    monkeypatch.setenv('OPENAI_SMART_SEARCH_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder-not-a-real-key')
    _call_times.clear()
    yield
    _call_times.clear()


def preference(query, level=None, maximum=None, captions=False):
    return {'query': query, 'level': level, 'max_talks': maximum, 'captioned_only': captions}


def payload():
    return {'day_1': preference('kubernetes security', ['beginner', 'intermediate'], 2),
            'day_2': preference('observability tracing', 'advanced', 1, True),
            'day_3': preference('platform engineering', None, 3)}


def model_response(data):
    import json
    response = Mock()
    response.json.return_value = {'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(data)}]}]}
    return response


def session(identifier, day, query, start='09:00', end='09:30', level='beginner', captions=True):
    return {'id': identifier, 'title': query, 'speaker': 'Demo Speaker', 'track': 'Security',
            'description': query, 'tags': query.split(), 'level': level,
            'start': f'{day}T{start}:00-07:00', 'end': f'{day}T{end}:00-07:00', 'room': 'A',
            'accessibility': {'captioned': captions, 'step_free': None, 'plain_language_summary': None}}


def retrieval_result(talks, mode='keyword', source='elasticsearch'):
    return {'talks': talks, 'total': len(talks), 'source': source, 'mode': mode,
            'degraded_reason': None, 'requested_mode': 'auto', 'took_ms': 1, 'facets': {}}


def daily_retrieval(**kwargs):
    day, query = kwargs['day'], kwargs['q']
    if day == '2026-11-10':
        return retrieval_result([
            session('first', day, query, '09:00', '10:00'),
            session('clash', day, query, '09:30', '10:15', 'intermediate'),
            session('back-to-back', day, query, '10:00', '10:30', 'any level'),
            session('past-cap', day, query, '11:00', '11:30')])
    if day == '2026-11-11':
        return retrieval_result([session('middle', day, query, level='advanced')], mode='hybrid')
    return retrieval_result([session(f'last-{i}', day, query, f'{9+i:02}:00', f'{9+i:02}:30') for i in range(5)])


def test_one_request_one_model_call_and_independent_daily_constraints():
    with patch('app.smart_search.httpx.post', return_value=model_response(payload())) as post, \
         patch('app.main.search_result', side_effect=daily_retrieval) as retrieve, TestClient(app) as client:
        response = client.post('/api/build-conference', json={'interests':
            'Day 1 beginner and medium Kubernetes security max 2. Day 2 advanced observability max 1 '
            'captioned. Day 3 platform engineering max 3.'})
    assert response.status_code == 200
    data = response.json()
    assert post.call_count == 1 and retrieve.call_count == 3
    assert data['extraction_calls'] == 1 and data['interpretation_source'] == 'openai'
    assert [day['day'] for day in data['days']] == ['2026-11-10', '2026-11-11', '2026-11-12']
    assert [day['total'] for day in data['days']] == [2, 1, 3]
    assert [call.kwargs['q'] for call in retrieve.call_args_list] == [
        'kubernetes security', 'observability tracing', 'platform engineering']
    assert retrieve.call_args_list[0].kwargs['level'] == ['beginner', 'intermediate', 'any level']
    assert retrieve.call_args_list[1].kwargs['level'] == 'advanced'
    assert retrieve.call_args_list[1].kwargs['captioned_only'] is True
    assert data['days'][1]['mode'] == 'hybrid'
    assert data['days'][0]['talks'][1]['id'] == 'back-to-back'
    for day in data['days']:
        assert day['status'] == 'ok' and day['clashes'] == []
        assert all(talk['start'].startswith(day['day']) for talk in day['talks'])
        assert all(not overlaps(a, b) for a, b in combinations(day['talks'], 2))
    body = post.call_args.kwargs['json']
    assert body['store'] is False and body['text']['format']['strict'] is True
    assert body['text']['format']['name'] == 'three_day_conference_intent'


def test_empty_day_keeps_successful_days_visible_and_truthful():
    def retrieve(**kwargs):
        return retrieval_result([]) if kwargs['day'] == '2026-11-11' else daily_retrieval(**kwargs)
    with patch('app.smart_search.httpx.post', return_value=model_response(payload())), \
         patch('app.main.search_result', side_effect=retrieve), TestClient(app) as client:
        data = client.post('/api/build-conference', json={'interests': 'Plan all three days'}).json()
    assert [day['status'] for day in data['days']] == ['ok', 'empty', 'ok']
    assert data['days'][1]['talks'] == []
    assert 'No matching sessions' in data['days'][1]['selection_note']
    assert data['days'][1]['source'] == 'elasticsearch'


def test_daily_retrieval_failure_is_isolated_and_sanitized():
    def retrieve(**kwargs):
        if kwargs['day'] == '2026-11-11':
            raise TimeoutError('sensitive server endpoint')
        return daily_retrieval(**kwargs)
    with patch('app.smart_search.httpx.post', return_value=model_response(payload())), \
         patch('app.main.search_result', side_effect=retrieve), TestClient(app) as client:
        response = client.post('/api/build-conference', json={'interests': 'Plan all three days'})
    data = response.json()
    assert response.status_code == 200
    assert [day['status'] for day in data['days']] == ['ok', 'error', 'ok']
    assert data['days'][1]['source'] == 'unavailable' and data['days'][1]['mode'] == 'none'
    assert 'sensitive' not in response.text


def test_unspecified_day_does_not_invent_a_topic_or_run_search():
    parsed = payload()
    parsed['day_2'] = preference('')
    with patch('app.smart_search.httpx.post', return_value=model_response(parsed)), \
         patch('app.main.search_result', side_effect=daily_retrieval) as retrieve, TestClient(app) as client:
        data = client.post('/api/build-conference', json={'interests': 'Plan Day 1 and Day 3'}).json()
    assert retrieve.call_count == 2
    assert data['days'][1]['source'] == 'not_queried' and data['days'][1]['mode'] == 'none'
    assert data['days'][1]['status'] == 'empty'


def test_fallback_label_survives_daily_scheduling():
    def retrieve(**kwargs):
        result = daily_retrieval(**kwargs)
        result['source'] = 'fallback'
        return result
    with patch('app.smart_search.httpx.post', return_value=model_response(payload())), \
         patch('app.main.search_result', side_effect=retrieve), TestClient(app) as client:
        data = client.post('/api/build-conference', json={'interests': 'Plan all three days'}).json()
    assert all(day['source'] == 'fallback' and day['degraded_reason'] for day in data['days'])


def test_daily_selection_cannot_leak_wrong_date_level_or_captions():
    def retrieve(**kwargs):
        if kwargs['day'] != '2026-11-10':
            return daily_retrieval(**kwargs)
        query = kwargs['q']
        return retrieval_result([
            session('allowed', '2026-11-10', query),
            session('wrong-date', '2026-11-11', query, '10:00', '10:30'),
            session('wrong-level', '2026-11-10', query, '11:00', '11:30', 'advanced'),
            session('no-captions', '2026-11-10', query, '12:00', '12:30', captions=False)])
    with patch('app.smart_search.httpx.post', return_value=model_response(payload())), \
         patch('app.main.search_result', side_effect=retrieve), TestClient(app) as client:
        data = client.post('/api/build-conference', json={
            'interests': 'Plan all three days', 'captioned_only': True}).json()
    assert [talk['id'] for talk in data['days'][0]['talks']] == ['allowed']
    assert data['days'][0]['interpretation']['captioned_only'] is True


@pytest.mark.parametrize('body', [
    {'status': 'incomplete'},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
])
def test_bad_extraction_fails_explicitly_without_search(body):
    response = Mock()
    response.json.return_value = body
    with patch('app.smart_search.httpx.post', return_value=response) as post, \
         patch('app.main.search_result') as retrieve, TestClient(app) as client:
        result = client.post('/api/build-conference', json={'interests': 'Plan all three days'})
    assert result.status_code == 503 and post.call_count == 1
    retrieve.assert_not_called()


def test_missing_key_and_blank_input_make_no_model_request(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    with patch('app.smart_search.httpx.post') as post, TestClient(app) as client:
        assert client.post('/api/build-conference', json={'interests': 'Day 1 security'}).status_code == 503
        assert client.post('/api/build-conference', json={'interests': '   '}).status_code == 422
    post.assert_not_called()
