"""Opt-in live three-day acceptance. Creates and deletes three test daily plans."""
import json
import os
import secrets
from datetime import datetime
from urllib.request import Request, urlopen

BASE = os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/')
EXAMPLE = (
    'Plan all three conference days. '
    'Day 1: beginner and intermediate Kubernetes and security, maximum 3 sessions. '
    'Day 2: observability, tracing and OpenTelemetry, any level, maximum 2 sessions. '
    'Day 3: platform engineering and developer experience, any level, maximum 4 sessions.'
)


def request(path, method='GET', payload=None, planner_key=None):
    headers = {'Content-Type': 'application/json'}
    if planner_key:
        headers['X-Planner-Key'] = planner_key
    body = None if payload is None else json.dumps(payload).encode()
    with urlopen(Request(BASE + path, data=body, headers=headers, method=method), timeout=90) as response:
        return json.load(response)


def main():
    data = request('/api/build-conference', 'POST', {'interests': EXAMPLE, 'mode': 'auto'})
    assert len(data['days']) == 3, 'Expected three dated results'
    assert data['interpretation_source'] == 'openai', 'Not a real OpenAI interpretation'
    assert data['extraction_calls'] == 1, 'Expected one structured extraction call'
    expected_dates = ['2026-11-10', '2026-11-11', '2026-11-12']
    for day, expected_date, cap in zip(data['days'], expected_dates, [3, 2, 4]):
        assert day['day'] == expected_date
        assert day['max_talks'] == cap
        assert day['source'] == 'elasticsearch', f"{expected_date} did not use Elasticsearch"
        assert 0 < len(day['talks']) <= cap, f"No matching sessions for {expected_date}"
        assert all(talk['start'].startswith(expected_date) for talk in day['talks'])
        level = day.get('effective_level')
        allowed = level if isinstance(level, list) else [level]
        assert not level or all(talk['level'] in allowed for talk in day['talks'])
        assert all(datetime.fromisoformat(a['end']) <= datetime.fromisoformat(b['start'])
                   for a, b in zip(day['talks'], day['talks'][1:])), 'Overlapping sessions'
        print(f"PASS: {expected_date}, {len(day['talks'])}/{cap} sessions, {day['mode']}, Elasticsearch")

    key = secrets.token_hex(32)
    created = []
    try:
        for day in data['days']:
            ids = [talk['id'] for talk in day['talks']]
            plan = request('/api/plans', 'POST', {
                'name': 'Multi-day acceptance ' + day['day'], 'day': day['day'], 'talk_ids': ids}, key)
            created.append(plan['id'])
            loaded = request('/api/plans/' + plan['id'], planner_key=key)
            assert loaded['day'] == day['day'] and loaded['talk_ids'] == ids
        listed = request('/api/plans', planner_key=key)
        assert len(listed['plans']) == 3
        assert {plan['day'] for plan in listed['plans']} == set(expected_dates)
        print('PASS: three independent daily plans saved and reopened')
    finally:
        for plan_id in created:
            assert request('/api/plans/' + plan_id, 'DELETE', planner_key=key)['deleted']
    print('PASS: temporary acceptance plans removed')


if __name__ == '__main__':
    main()
