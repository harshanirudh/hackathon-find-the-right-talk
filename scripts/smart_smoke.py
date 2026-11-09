"""Opt-in live OpenAI + Elasticsearch verification; incurs an inference call."""
from datetime import datetime
from smoke import check, request


def main():
    day = request('/api/build-my-day', {
        'interests': 'beginer kubernets atmost 3 sessions', 'smart': True, 'day': '2026-11-10'})
    check(day['interpretation']['source'] == 'openai', 'OpenAI did not succeed: ' + str(day['interpretation']))
    check(day['source'] == 'elasticsearch', 'Retrieval used fallback')
    check(day['max_talks'] == 3 and 0 < len(day['talks']) <= 3, 'Three-session cap failed')
    check(all(t['level'] == 'beginner' and t['start'].startswith('2026-11-10') for t in day['talks']),
          'Day or experience filter failed')
    check(all(datetime.fromisoformat(a['end']) <= datetime.fromisoformat(b['start'])
              for a, b in zip(day['talks'], day['talks'][1:])), 'Day contains overlaps')
    search = request('/api/search?q=beginer+kubernets+atmost+3+sessions&smart=true')
    check(search['interpretation']['source'] == 'openai' and search['source'] == 'elasticsearch',
          'Smart search source labels are incorrect')
    check(0 < len(search['talks']) <= 3 and search['total'] <= 3, 'Search cap failed')
    print(f"PASS: real OpenAI interpretation ({day['interpretation']['model']}), Elasticsearch retrieval, "
          f"beginner filter, three-session cap, {len(day['talks'])} compatible sessions")


if __name__ == '__main__':
    main()
