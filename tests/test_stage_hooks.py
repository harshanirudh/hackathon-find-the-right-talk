from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.data import TALKS
from app.main import app
from app.store import Store
from app.stages import stage


def test_stage_sanitizes_errors_and_preserves_parent_child_context():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with patch('app.stages.trace.get_tracer', return_value=provider.get_tracer('test')):
        try:
            with stage('parent'):
                with stage('child', **{'planner.day': '2026-11-10'}):
                    raise ValueError('raw secret prompt must not be exported')
        except ValueError:
            pass
    child, parent = exporter.get_finished_spans()
    assert child.parent.span_id == parent.context.span_id
    assert child.attributes['stage.outcome'] == 'error'
    assert child.attributes['error.type'] == 'ValueError'
    assert child.attributes['stage.duration_ms'] >= 0
    assert not child.events
    assert 'raw secret' not in str(child.attributes)


def test_hybrid_can_reuse_keyword_preflight_without_another_keyword_request():
    store = Store.__new__(Store)
    store.client = Mock()
    store.semantic_provider = 'elastic'
    store._elastic_hybrid_search = Mock(return_value={'talks': TALKS[:2], 'mode': 'hybrid'})
    prefetched = (TALKS[:3], 'elasticsearch', 3, {'track': []})
    result = store.hybrid_search('diagnose sluggish requests', prefetched_keyword=prefetched)
    assert result['mode'] == 'hybrid'
    store.client.search.assert_not_called()
    assert store._elastic_hybrid_search.call_args.args[1] == TALKS[:3]


def test_auto_only_reuses_compatible_first_keyword_page():
    with patch('app.main.store') as store, TestClient(app) as client:
        store.search_page.return_value = (TALKS[:3], 'elasticsearch', 3, {})
        store.hybrid_search.return_value = {'talks': TALKS[:3], 'source': 'elasticsearch', 'mode': 'hybrid'}
        client.get('/api/search', params={'q': 'diagnose sluggish requests', 'mode': 'auto', 'limit': 3})
        assert store.hybrid_search.call_args.kwargs['prefetched_keyword'][0] == TALKS[:3]
        store.search_page.return_value = (TALKS[3:5], 'elasticsearch', 28, {})
        client.get('/api/search', params={'q': 'diagnose sluggish requests', 'mode': 'auto', 'limit': 2, 'offset': 3})
        assert 'prefetched_keyword' not in store.hybrid_search.call_args.kwargs


def test_openai_usage_and_cache_hit_do_not_claim_extra_api_calls(monkeypatch):
    import json
    from app.smart_search import _call_times, _extract, interpret_request
    monkeypatch.setenv('OPENAI_SMART_SEARCH_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder-not-a-real-key')
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    response = Mock()
    intent = {'query': 'kubernetes', 'level': 'beginner', 'max_talks': 3,
              'captioned_only': False, 'day': None}
    response.json.return_value = {'status': 'completed',
        'usage': {'input_tokens': 101, 'output_tokens': 31},
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(intent)}]}]}
    _extract.cache_clear()
    _call_times.clear()
    try:
        with patch('app.stages.trace.get_tracer', return_value=provider.get_tracer('test')), \
             patch('app.smart_search.httpx.post', return_value=response) as post:
            assert interpret_request('beginner Kubernetes max 3', True)['source'] == 'openai'
            assert interpret_request('beginner Kubernetes max 3', True)['source'] == 'openai'
        assert post.call_count == 1
        spans = exporter.get_finished_spans()
        stages = [span for span in spans if span.name == 'planner.interpret']
        calls = [span for span in spans if span.name == 'search.interpret']
        assert [span.attributes['interpretation.cache.hit'] for span in stages] == [False, True]
        assert len(calls) == 1 and calls[0].parent.span_id == stages[0].context.span_id
        assert calls[0].attributes['gen_ai.usage.input_tokens'] == 101
        assert calls[0].attributes['gen_ai.usage.output_tokens'] == 31
        assert calls[0].attributes['interpretation.api_call'] is True
        assert all('beginner Kubernetes max 3' not in str(span.attributes) for span in spans)
    finally:
        _extract.cache_clear()
        _call_times.clear()
        provider.shutdown()
