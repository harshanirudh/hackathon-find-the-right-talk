import json
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.smart_search import SearchIntent, _extract, _call_times, interpret_request
from app.data import TALKS
from app.search import fallback_search


@pytest.fixture(autouse=True)
def isolated_ai(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-a-real-key')
    monkeypatch.setenv('OPENAI_SMART_SEARCH_ENABLED', 'true')
    _extract.cache_clear()
    _call_times.clear()
    yield
    _extract.cache_clear()
    _call_times.clear()


def intent(**changes):
    return SearchIntent(**{'query': 'kubernetes', 'level': 'beginner', 'max_talks': 3,
                           'captioned_only': False, 'day': None, **changes})


def test_opt_out_and_missing_configuration_make_no_requests(monkeypatch):
    with patch('app.smart_search.httpx.post') as post:
        assert interpret_request('beginer kubernets atmost 3 sessions')['source'] == 'rules'
        monkeypatch.delenv('OPENAI_API_KEY')
        result = interpret_request('kubernetes', True)
        assert result['source'] == 'rules' and result['degraded_reason']
        post.assert_not_called()


def test_structured_response_is_validated_and_success_is_cached():
    response = Mock()
    response.json.return_value = {'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': intent().model_dump_json()}]}]}
    with patch('app.smart_search.httpx.post', return_value=response) as post:
        for _ in range(2):
            result = interpret_request('beginer kubernets atmost 3 sessions', True)
            assert result['source'] == 'openai' and result['max_talks'] == 3
        assert post.call_count == 1
        payload = post.call_args.kwargs['json']
        assert payload['store'] is False
        assert payload['text']['format']['strict'] is True
        assert 'test-not-a-real-key' not in json.dumps(payload)


@pytest.mark.parametrize('body', [
    {'status': 'incomplete'},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': '{"query":"kubernetes","max_talks":-3}'}]}]},
])
def test_bad_model_output_uses_labelled_basic_fallback(body):
    response = Mock()
    response.json.return_value = body
    with patch('app.smart_search.httpx.post', return_value=response):
        result = interpret_request('beginer kubernets atmost 3 sessions', True)
        assert result['source'] == 'rules' and result['degraded_reason']
        assert result['query'] == 'kubernetes' and result['max_talks'] == 3


def test_timeout_never_leaks_sensitive_errors_and_is_not_cached():
    with patch('app.smart_search.httpx.post', side_effect=httpx.ReadTimeout('SECRET')) as post:
        for _ in range(2):
            result = interpret_request('kubernetes max 3', True)
            assert result['source'] == 'rules' and 'SECRET' not in str(result)
        assert post.call_count == 2


def test_model_cannot_relax_a_parsed_cap():
    with patch('app.smart_search._extract', return_value=intent(max_talks=20)):
        assert interpret_request('kubernetes max 3', True)['max_talks'] == 3


def test_smart_day_preserves_explicit_filters_date_cap_and_no_overlap():
    with patch('app.main.store') as store, patch('app.smart_search._extract', return_value=intent()), TestClient(app) as client:
        def results(**kw):
            talks = fallback_search(TALKS, kw['q'], kw['track'], kw['level'], kw['captioned_only'])
            return talks, 'elasticsearch', len(talks), {}
        store.search_page.side_effect = results
        data = client.post('/api/build-my-day', json={
            'interests': 'beginer kubernets atmost 3 sessions', 'smart': True,
            'level': 'intermediate', 'day': '2026-11-09', 'captioned_only': True}).json()
        assert data['interpretation']['source'] == 'openai'
        assert data['effective_level'] == 'intermediate' and data['max_talks'] == 3
        assert len(data['talks']) <= 3 and data['clashes'] == []
        kw = store.search_page.call_args.kwargs
        assert str(kw['day']) == '2026-11-09' and kw['captioned_only'] is True
        assert kw['level'] == 'intermediate'


def test_smart_search_caps_pagination_and_keeps_elasticsearch_as_source():
    with patch('app.main.store') as store, patch('app.smart_search._extract', return_value=intent()), TestClient(app) as client:
        store.search_page.return_value = (TALKS[:3], 'elasticsearch', 50, {})
        data = client.get('/api/search', params={'q': 'beginer kubernets atmost 3 sessions', 'smart': True}).json()
        assert data['source'] == 'elasticsearch' and data['interpretation']['source'] == 'openai'
        assert data['total'] == 3 and len(data['talks']) == 3
        assert store.search_page.call_args.kwargs['q'] == 'kubernetes'
        assert store.search_page.call_args.kwargs['size'] == 3
        data = client.get('/api/search', params={'q': 'same request', 'smart': True, 'offset': 3}).json()
        assert data['talks'] == []


def test_call_budget_falls_back_without_network():
    from time import monotonic
    _call_times.extend([monotonic()] * 20)
    with patch('app.smart_search.httpx.post') as post:
        assert interpret_request('kubernetes', True)['source'] == 'rules'
        post.assert_not_called()


@pytest.mark.parametrize('smart', [False, True])
def test_level_only_request_browses_without_inventing_a_topic(smart):
    with patch('app.main.store') as store, patch('app.smart_search._extract', return_value=intent(query='', max_talks=7)), TestClient(app) as client:
        from tests.test_core import talk
        candidates = [talk('a', '10:00', '10:30'), talk('b', '10:00', '10:30'),
                      talk('c', '11:00', '11:30'), talk('d', '12:00', '12:30')]
        store.search_page.return_value = (candidates, 'elasticsearch', 4, {})
        response = client.post('/api/build-my-day', json={
            'interests': 'beginner session atmost 7', 'smart': smart, 'day': '2026-11-09'})
        assert response.status_code == 200
        data = response.json()
        assert data['interests'] == '' and data['max_talks'] == 7
        assert data['candidate_count'] == 4 and data['total'] == 3
        assert '3 compatible sessions from 4' in data['selection_note']
        assert store.search_page.call_args.kwargs['q'] == ''
        assert store.search_page.call_args.kwargs['level'] == 'beginner'
        assert all('Retrieved by meaning' not in t['reason'] for t in data['talks'])


def test_hybrid_search_obeys_limit_and_offset():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.hybrid_search.return_value = {'talks': TALKS[:3], 'source': 'elasticsearch', 'mode': 'hybrid'}
        data = client.get('/api/search', params={'q': 'security', 'mode': 'hybrid', 'limit': 1, 'offset': 1}).json()
        assert data['total'] == 3
        assert [t['id'] for t in data['talks']] == [TALKS[1]['id']]


def test_mixed_experience_request_keeps_both_levels_and_five_session_cap():
    phrase = 'beginer friendly and medium day 1 with 5 sessions covering essential on kubernetes and security'
    mixed = intent(query='kubernetes security', level=['beginner', 'intermediate'], max_talks=5, day='2026-11-10')
    with patch('app.main.store') as store, patch('app.smart_search._extract', return_value=mixed), TestClient(app) as client:
        from tests.test_core import talk
        candidates = [talk(str(i), start=f'{9+i:02}:00', end=f'{9+i:02}:30',
                           level='beginner' if i % 2 == 0 else 'intermediate') for i in range(7)]
        store.search_page.return_value = (candidates, 'elasticsearch', 7, {})
        response = client.post('/api/build-my-day', json={'interests': phrase, 'smart': True, 'day': '2026-11-09'})
        assert response.status_code == 200
        data = response.json()
        assert data['effective_level'] == ['beginner', 'intermediate', 'any level']
        assert data['max_talks'] == 5 and len(data['talks']) == 5
        assert {t['level'] for t in data['talks']} == {'beginner', 'intermediate'}
        assert store.search_page.call_args.kwargs['level'] == ['beginner', 'intermediate', 'any level']


def test_multiple_levels_are_validated_in_real_structured_response():
    response = Mock()
    response.json.return_value = {'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': intent(level=['beginner', 'intermediate']).model_dump_json()}]}]}
    with patch('app.smart_search.httpx.post', return_value=response):
        assert interpret_request('beginner and medium kubernetes max 3', True)['level'] == ['beginner', 'intermediate']


def test_active_plan_date_wins_when_browsing_a_smart_query():
    with patch('app.main.store') as store, patch('app.smart_search._extract', return_value=intent(day='2026-11-10')), TestClient(app) as client:
        store.search_page.return_value = ([], 'elasticsearch', 0, {})
        response = client.get('/api/search', params={
            'q': 'beginner kubernetes', 'smart': True, 'day': '2026-11-11'})
        assert response.status_code == 200
        assert store.search_page.call_args.kwargs['day'] == '2026-11-11'
        assert response.json()['day'] == '2026-11-11'
        assert response.json()['interpretation']['day'] == '2026-11-11'
