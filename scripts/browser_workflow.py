"""Deterministic UI workflow regressions; all API responses are mocked in-browser."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/')


def talk(identifier, title, hour=10):
    return {'id': identifier, 'title': title, 'speaker': 'Demo Speaker', 'track': 'Security',
            'level': 'beginner', 'description': 'Kubernetes security fundamentals',
            'tags': ['kubernetes'], 'start': f'2026-11-10T{hour:02}:00:00-07:00',
            'end': f'2026-11-10T{hour:02}:30:00-07:00', 'room': 'Demo room',
            'accessibility': {'captioned': True, 'step_free': None, 'plain_language_summary': None}}


def main():
    items = [talk('a', 'Kubernetes foundations'), talk('b', 'Kubernetes security', 11),
             talk('c', 'Other programme talk', 12)]
    other_day = {**talk('next-day', 'Next day session'), 'start': '2026-11-11T10:00:00-07:00', 'end': '2026-11-11T10:30:00-07:00'}
    records = {item['id']: item for item in items}
    records[other_day['id']] = other_day
    plans, held = {}, {}
    base_result = {'source': 'elasticsearch', 'mode': 'keyword', 'took_ms': 12,
                   'facets': {}, 'degraded_reason': None}
    built = {**base_result, 'talks': items[:2], 'total': 2, 'max_talks': 3,
             'day': '2026-11-10', 'interests': 'kubernetes', 'selection_note': '',
             'effective_level': ['beginner', 'intermediate'],
             'interpretation': {'query': 'kubernetes', 'level': ['beginner', 'intermediate'],
                                'max_talks': 3, 'captioned_only': False, 'day': '2026-11-10',
                                'source': 'openai', 'degraded_reason': None}}

    def respond(route, body, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        args = parse_qs(urlparse(request.url).query)
        payload = request.post_data_json if request.method in ('POST', 'PUT') else {}
        if path == '/api/search':
            if int(args.get('offset', ['0'])[0]):
                held['page'] = route
                return
            data = [other_day] if args.get('q') == ['next-day'] else [items[2]] if args.get('q') == ['B'] else items[:2]
            respond(route, {**base_result, 'talks': data, 'total': len(data) if args.get('q') in (['B'], ['next-day']) else 3})
        elif path == '/api/places':
            respond(route, {'source': 'elasticsearch', 'places': [], 'total': 0})
        elif path == '/api/build-my-day':
            assert payload['mode'] == 'auto'
            if payload['interests'] == 'slow':
                held['build'] = route
            elif payload['interests'] == 'build a intermediate plan on kubernetes only':
                respond(route, {**built, 'talks': [], 'total': 0, 'day': '2026-11-11',
                                'effective_level': 'intermediate',
                                'interpretation': {**built['interpretation'], 'level': 'intermediate', 'day': '2026-11-11'}})
            else:
                respond(route, built)
        elif path == '/api/agenda':
            ids = payload['talk_ids']
            if any(identifier not in records for identifier in ids):
                respond(route, {'detail': 'Unknown talk IDs: missing'}, 422)
            else:
                respond(route, {'source': 'elasticsearch', 'talks': [records[i] for i in ids], 'clashes': [], 'alternatives': {}})
        elif path == '/api/plans' and request.method == 'POST':
            plans['test-plan'] = {**payload, 'id': 'test-plan', 'talk_count': len(payload['talk_ids']), 'talks': [records[i] for i in payload['talk_ids']]}
            respond(route, {**plans['test-plan'], 'source': 'elasticsearch'})
        elif path == '/api/plans':
            respond(route, {'source': 'elasticsearch', 'plans': list(plans.values())})
        elif path == '/api/plans/test-plan' and request.method == 'PUT':
            plans['test-plan'].update(payload)
            respond(route, {**plans['test-plan'], 'source': 'elasticsearch'})
        elif path == '/api/plans/test-plan':
            respond(route, {**plans['test-plan'], 'source': 'elasticsearch'})
        else:
            respond(route, {'detail': 'Unexpected mocked endpoint'}, 500)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(10000)
        page.route('**/api/**', api)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.locator('#search-mode')).to_have_count(0)
        expect(page.locator('#day-mode')).to_have_count(0)
        expect(page.locator('.agenda-item')).to_have_count(0)
        expect(page.locator('.agenda-save')).to_be_hidden()
        page.locator('#interests').fill('kubernetes max 3')
        page.locator('#build-button').click()
        expect(page.locator('.agenda-item')).to_have_count(2)
        expect(page.locator('.talk-card')).to_have_count(2)
        expect(page.locator('#browse-controls')).to_be_hidden()
        expect(page.locator('#source')).to_contain_text('2 results')
        expect(page.locator('#day-interpretation')).to_contain_text('beginner + intermediate')
        expect(page.locator('#notice')).to_contain_text('Experience: beginner + intermediate')
        expect(page.locator('#save-plan-button')).to_be_visible()
        page.locator('#plan-name').fill('My security day')
        page.locator('#save-plan-button').click()
        expect(page.locator('#plan-save-status')).to_contain_text('Saved as')
        expect(page.locator('#notice')).to_contain_text('Your plan is saved in Elasticsearch')
        expect(page.locator('#day-panel')).to_be_visible()
        page.locator('#saved-library').evaluate('node => node.open = true')
        page.locator('[data-load-plan="test-plan"]').click()
        expect(page.locator('#day-panel')).to_be_visible()
        page.locator('#plan-name').fill('Edited day')
        page.locator('#save-plan-button').click()
        expect(page.locator('#plan-save-status')).to_contain_text('Edited day')
        assert plans['test-plan']['name'] == 'Edited day'
        earlier_ids = page.evaluate("localStorage.getItem('righttalk-agenda')")
        page.locator('#conference-day').select_option('2026-11-11')
        page.locator('#interests').fill('build a intermediate plan on kubernetes only')
        page.locator('#build-button').click()
        expect(page.locator('#discover-title')).to_have_text('No matching sessions · Nov 11')
        expect(page.locator('.talk-card')).to_have_count(0)
        expect(page.locator('#source')).to_contain_text('0 results')
        expect(page.locator('.agenda-item')).to_have_count(2)
        expect(page.locator('.date-line')).to_contain_text('Nov 10')
        expect(page.locator('#retained-draft-note')).to_contain_text('Existing Nov 10 draft kept')
        expect(page.locator('#retained-draft-note')).to_contain_text('latest Nov 11 request found no matches')
        expect(page.locator('#plan-name')).to_have_value('Edited day')
        expect(page.locator('#save-plan-button')).to_have_text('Save changes')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == earlier_ids
        output = Path(__file__).resolve().parents[1] / 'artifacts'
        output.mkdir(exist_ok=True)
        page.screenshot(path=str(output / 'workflow-empty-request.png'), full_page=True)
        page.locator('#browse-program').click()
        expect(page.locator('#browse-controls')).to_be_visible()
        page.locator('#query').fill('next-day')
        page.locator('#search-form').evaluate('form => form.requestSubmit()')
        expect(page.locator('[data-add="next-day"]')).to_be_visible()
        page.locator('[data-add="next-day"]').click()
        expect(page.locator('#notice')).to_contain_text('This plan is for 2026-11-10')
        expect(page.locator('.agenda-item')).to_have_count(2)
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '["a","b"]'
        page.locator('#saved-library').evaluate('node => node.open = true')
        page.locator('[data-load-plan="test-plan"]').click()
        expect(page.locator('#day-panel')).to_be_visible()
        output = Path(__file__).resolve().parents[1] / 'artifacts'
        output.mkdir(exist_ok=True)
        page.screenshot(path=str(output / 'workflow-desktop.png'), full_page=True)
        help_button = page.get_by_role('button', name='How day planning works', exact=True)
        help_button.focus()
        expect(page.locator('#feature-tooltip')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#feature-tooltip')).to_be_hidden()
        help_button.click()
        expect(page.locator('#feature-tooltip')).to_be_visible()
        help_button.click()
        expect(page.locator('#feature-tooltip')).to_be_hidden()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output / 'workflow-mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('#interests').fill('slow')
        with page.expect_request('**/api/build-my-day'):
            page.locator('#build-button').click()
        page.locator('#clear-agenda').click()
        respond(held.pop('build'), built)
        expect(page.locator('#notice')).to_contain_text('Your current choices were kept')
        expect(page.locator('.agenda-item')).to_have_count(0)
        expect(page.locator('#save-plan-button')).to_have_text('Save plan')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '[]'
        page.locator('#browse-program').click()
        expect(page.locator('.show-more')).to_be_visible()
        with page.expect_request(lambda request: '/api/search?' in request.url and 'offset=2' in request.url):
            page.locator('.show-more').click()
        page.locator('#query').fill('B')
        page.locator('#search-form').evaluate('form => form.requestSubmit()')
        expect(page.locator('.talk-card h3')).to_have_text(['Other programme talk'])
        respond(held.pop('page'), {**base_result, 'talks': [items[0]], 'total': 3})
        expect(page.locator('.talk-card')).to_have_count(1)
        page.evaluate("localStorage.setItem('righttalk-agenda', JSON.stringify(['missing']))")
        page.reload()
        expect(page.locator('#agenda-status')).to_contain_text('Clash check unavailable')
        expect(page.locator('#clear-agenda')).to_be_enabled()
        expect(page.locator('#draft-origin')).to_be_visible()
        page.locator('#clear-agenda').click()
        expect(page.locator('#agenda-status')).to_contain_text('blank canvas')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '[]'
        page.evaluate("localStorage.setItem('righttalk-agenda', JSON.stringify(['a', 'next-day']))")
        page.reload()
        expect(page.locator('#agenda-status')).to_contain_text('Clash check unavailable')
        expect(page.locator('#clear-agenda')).to_be_enabled()
        page.locator('#clear-agenda').click()
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '[]'
        assert not errors, errors
        browser.close()
    print('PASS: mocked inline build/open/edit/save library, empty latest request with retained earlier draft, mixed-level labels, automatic mode, cross-day rejection, async guards, restore recovery, tooltips, mobile')


if __name__ == '__main__':
    main()
