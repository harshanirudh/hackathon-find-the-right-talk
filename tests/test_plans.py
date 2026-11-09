"""Saved plans require Elasticsearch and isolate each private key's plans."""
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, plan_owner_hash
from app.store import Store

KEY = 'a' * 64
HEADERS = {'X-Planner-Key': KEY}


@pytest.fixture
def api_store():
    with patch('app.main.store') as store, TestClient(app) as client:
        yield client, store


def test_plan_access_requires_valid_key(api_store):
    client, store = api_store
    for headers in ({}, {'X-Planner-Key': 'x' * 64}):
        assert client.get('/api/plans', headers=headers).status_code == 422
    store.list_plans.assert_not_called()


def test_save_deduplicates_and_checks_indexed_talks(api_store):
    client, store = api_store
    store.get_talks_by_ids.return_value = [{'id': 'one', 'start': '2026-11-10T10:00:00-07:00'}]
    store.create_plan.return_value = {'id': 'plan', 'name': 'My plan', 'talk_ids': ['one']}
    response = client.post('/api/plans', headers=HEADERS,
                           json={'name': ' My plan ', 'talk_ids': ['one', 'one']})
    assert response.status_code == 200
    assert response.json()['source'] == 'elasticsearch'
    store.create_plan.assert_called_once_with(plan_owner_hash(KEY), 'My plan', ['one'], '2026-11-10')
    store.get_talks_by_ids.return_value = []
    assert client.post('/api/plans', headers=HEADERS,
                       json={'name': 'Missing', 'talk_ids': ['unknown']}).status_code == 422
    assert store.create_plan.call_count == 1


def test_plan_outage_is_explicit_and_sanitized(api_store):
    client, store = api_store
    store.list_plans.side_effect = ConnectionError('secret endpoint')
    response = client.get('/api/plans', headers=HEADERS)
    assert response.status_code == 503
    assert 'Elasticsearch' in response.json()['detail']
    assert 'secret endpoint' not in response.text


def test_unknown_plan_cannot_be_loaded_updated_or_deleted(api_store):
    client, store = api_store
    store.get_plan.return_value = store.update_plan.return_value = None
    store.delete_plan.return_value = False
    store.get_talks_by_ids.return_value = [{'id': 'one', 'start': '2026-11-10T10:00:00-07:00'}]
    assert client.get('/api/plans/other', headers=HEADERS).status_code == 404
    assert client.put('/api/plans/other', headers=HEADERS,
                      json={'name': 'Changed', 'talk_ids': ['one']}).status_code == 404
    assert client.delete('/api/plans/other', headers=HEADERS).status_code == 404


def test_store_checks_owner_before_talk_lookup_or_mutation():
    store = Store.__new__(Store)
    store.client = Mock()
    store.client.get.return_value = {'_source': {'owner_hash': 'another-owner'}}
    assert store.get_plan(plan_owner_hash(KEY), 'other') is None
    assert store.update_plan(plan_owner_hash(KEY), 'other', 'Changed', ['one']) is None
    assert store.delete_plan(plan_owner_hash(KEY), 'other') is False
    store.client.index.assert_not_called()
    store.client.delete.assert_not_called()
    store.client.mget.assert_not_called()


def test_list_query_is_scoped_to_owner():
    store = Store.__new__(Store)
    store.client = Mock()
    store.client.search.return_value = {'hits': {'hits': []}}
    assert store.list_plans('owner') == []
    assert store.client.search.call_args.kwargs['query'] == {'term': {'owner_hash': 'owner'}}


def test_hybrid_beginner_request_passes_level_date_and_accessibility(api_store):
    client, store = api_store
    store.hybrid_search.return_value = {'talks': [], 'source': 'elasticsearch', 'mode': 'hybrid'}
    response = client.post('/api/build-my-day', json={
        'interests': 'new to kubernetes', 'mode': 'hybrid', 'captioned_only': True,
        'day': '2026-11-11'})
    assert response.status_code == 200
    args = store.hybrid_search.call_args.kwargs
    assert args['q'] == 'kubernetes' and args['level'] == 'beginner'
    assert args['captioned_only'] is True and str(args['day']) == '2026-11-11'


@pytest.mark.parametrize('method,path', [('post', '/api/plans'), ('put', '/api/plans/existing')])
def test_mixed_date_plans_cannot_be_saved_or_updated(api_store, method, path):
    client, store = api_store
    store.get_talks_by_ids.return_value = [
        {'id': 'one', 'start': '2026-11-10T10:00:00-07:00'},
        {'id': 'two', 'start': '2026-11-11T10:00:00-07:00'}]
    response = getattr(client, method)(path, headers=HEADERS,
        json={'name': 'My day', 'talk_ids': ['one', 'two']})
    assert response.status_code == 422
    assert 'one conference day' in response.json()['detail']
    store.create_plan.assert_not_called()
    store.update_plan.assert_not_called()


def test_plan_date_must_match_selected_sessions(api_store):
    client, store = api_store
    store.get_talks_by_ids.return_value = [{'id': 'one', 'start': '2026-11-11T10:00:00-07:00'}]
    response = client.post('/api/plans', headers=HEADERS,
        json={'name': 'Wrong date', 'talk_ids': ['one'], 'day': '2026-11-10'})
    assert response.status_code == 422
    store.create_plan.assert_not_called()


def test_legacy_mixed_day_plan_cannot_be_loaded_into_a_day(api_store):
    client, store = api_store
    store.get_plan.return_value = {'id': 'mixed', 'day': None, 'talks': [
        {'id': 'one', 'start': '2026-11-10T10:00:00-07:00'},
        {'id': 'two', 'start': '2026-11-11T10:00:00-07:00'}]}
    assert client.get('/api/plans/mixed', headers=HEADERS).status_code == 422
    store.delete_plan.assert_not_called()


def test_editing_saved_plan_cannot_move_it_to_another_day(api_store):
    client, store = api_store
    store.get_plan.return_value = {'day': '2026-11-10', 'talks': []}
    store.get_talks_by_ids.return_value = [{'id': 'two', 'start': '2026-11-11T10:00:00-07:00'}]
    response = client.put('/api/plans/existing', headers=HEADERS,
        json={'name': 'Different day', 'talk_ids': ['two'], 'day': '2026-11-11'})
    assert response.status_code == 422
    assert 'Save a new plan' in response.json()['detail']
    store.update_plan.assert_not_called()
