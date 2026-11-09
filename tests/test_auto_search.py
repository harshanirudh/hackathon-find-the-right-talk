from unittest.mock import patch

from fastapi.testclient import TestClient
from app.data import TALKS
from app.main import app


def test_auto_keeps_strong_literal_matches_as_keyword():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = (TALKS[:5], 'elasticsearch', 20, {})
        data = client.get('/api/search', params={'q': 'kubernetes security', 'mode': 'auto'}).json()
        assert data['mode'] == 'keyword' and data['requested_mode'] == 'auto'
        assert 'Strong literal matches' in data['strategy_reason']
        store.hybrid_search.assert_not_called()


def test_auto_uses_hybrid_for_weak_literal_results_and_keeps_filters():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = ([], 'elasticsearch', 0, {})
        store.hybrid_search.return_value = {'talks': TALKS[:3], 'source': 'elasticsearch', 'mode': 'hybrid'}
        data = client.get('/api/search', params={'q': 'sluggish requests', 'mode': 'auto',
            'level': 'beginner', 'captioned_only': True}).json()
        assert data['mode'] == 'hybrid' and data['requested_mode'] == 'auto'
        args = store.hybrid_search.call_args.kwargs
        assert args['level'] == 'beginner' and args['captioned_only'] is True


def test_auto_uses_hybrid_for_broad_language_even_with_many_lexical_hits():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = (TALKS[:5], 'elasticsearch', 20, {})
        store.hybrid_search.return_value = {'talks': TALKS[:3], 'source': 'elasticsearch', 'mode': 'hybrid'}
        data = client.get('/api/search', params={'q': 'find why requests are sluggish', 'mode': 'auto'}).json()
        assert data['mode'] == 'hybrid' and 'Natural-language request' in data['strategy_reason']


def test_auto_recognizes_short_natural_language_with_some_literal_matches():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = (TALKS[:5], 'elasticsearch', 8, {})
        store.hybrid_search.return_value = {'talks': TALKS[:3], 'source': 'elasticsearch', 'mode': 'hybrid'}
        data = client.get('/api/search', params={'q': 'diagnose sluggish microservices', 'mode': 'auto'}).json()
        assert data['mode'] == 'hybrid' and data['requested_mode'] == 'auto'


def test_auto_degradation_retains_keyword_page_and_total():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = (TALKS[5:7], 'elasticsearch', 20, {})
        store.hybrid_search.return_value = {'talks': TALKS[:5], 'source': 'elasticsearch',
            'mode': 'keyword', 'degraded_reason': 'Semantic service unavailable'}
        data = client.get('/api/search', params={'q': 'find why requests are sluggish',
            'mode': 'auto', 'offset': 5, 'limit': 2}).json()
        assert data['mode'] == 'keyword' and data['total'] == 20
        assert [t['id'] for t in data['talks']] == [t['id'] for t in TALKS[5:7]]
        assert data['degraded_reason']


def test_auto_browse_and_elasticsearch_outage_never_claim_hybrid():
    with patch('app.main.store') as store, TestClient(app) as client:
        for query, source in [('', 'elasticsearch'), ('sluggish requests', 'fallback')]:
            store.search_page.return_value = (TALKS[:3], source, 3, {})
            data = client.get('/api/search', params={'q': query, 'mode': 'auto'}).json()
            assert data['mode'] == 'keyword' and data['source'] == source
        store.hybrid_search.assert_not_called()
