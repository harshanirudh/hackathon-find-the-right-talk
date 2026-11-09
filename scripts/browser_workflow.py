"""Planner-first workflow regressions. Every API call is mocked; no paid calls or writes."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

BASE = os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/')
OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts'


def talk(identifier, title, hour=10, day='2026-11-10'):
    return {'id': identifier, 'title': title, 'speaker': 'Demo Speaker', 'track': 'Security',
            'level': 'beginner', 'description': 'Kubernetes security fundamentals. ' * 12,
            'tags': ['kubernetes'], 'start': f'{day}T{hour:02}:00:00-07:00',
            'end': f'{day}T{hour:02}:30:00-07:00', 'room': 'Demo room',
            'accessibility': {'captioned': True, 'step_free': None, 'plain_language_summary': None}}


def main():
    OUTPUT.mkdir(exist_ok=True)
    items = [talk('a', 'Kubernetes foundations'), talk('b', 'Kubernetes security', 11),
             talk('c', 'Other programme talk', 12)]
    other = talk('next-day', 'Next day session', day='2026-11-11')
    records = {item['id']: item for item in [*items, other]}
    plans, held = {}, {}
    post_count, updates = [0], []
    base_result = {'source': 'elasticsearch', 'mode': 'keyword', 'took_ms': 12,
                   'facets': {}, 'degraded_reason': None}
    built = {**base_result, 'talks': [{**item, 'reason': 'Matches Kubernetes; listed as beginner; no clash.'} for item in items[:2]],
             'total': 2, 'max_talks': 3, 'day': '2026-11-10', 'interests': 'kubernetes',
             'selection_note': '', 'effective_level': ['beginner', 'intermediate'],
             'interpretation': {'query': 'kubernetes', 'level': ['beginner', 'intermediate'],
                                'max_talks': 3, 'captioned_only': False, 'day': '2026-11-10',
                                'source': 'openai', 'degraded_reason': None}}
    searches = []

    def respond(route, body, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        args = parse_qs(urlparse(request.url).query)
        payload = request.post_data_json if request.method in ('POST', 'PUT') else {}
        if path == '/api/search':
            searches.append(args)
            assert args['mode'] == ['auto'] and args.get('day')
            if int(args.get('offset', ['0'])[0]):
                held['page'] = route
                return
            data = [other] if args.get('q') == ['next-day'] else [items[2]] if args.get('q') == ['B'] else items[:2]
            respond(route, {**base_result, 'talks': data, 'total': len(data) if args.get('q') in (['B'], ['next-day']) else 3})
        elif path == '/api/places':
            radius = int(args['radius_m'][0])
            places = [{'id': 'near', 'name': 'Nearby cafe', 'category': 'cafe', 'distance_m': 200,
                       'walking_minutes': 3, 'lat': 40.76, 'lon': -111.88, 'address': 'Demo address'}]
            if radius >= 1000:
                places.append({**places[0], 'id': 'far', 'name': 'Farther cafe', 'distance_m': 900, 'walking_minutes': 12})
            respond(route, {'source': 'elasticsearch', 'places': places, 'total': len(places), 'data_note': 'curated OSM fallback'})
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
            post_count[0] += 1
            identifier = 'test-plan' if post_count[0] == 1 else f'plan-{post_count[0]}'
            record = {**payload, 'id': identifier, 'talk_count': len(payload['talk_ids']), 'talks': [records[i] for i in payload['talk_ids']]}
            if payload['name'].startswith('Delayed'):
                held['save'] = (route, record)
            else:
                plans[identifier] = record
                respond(route, {**record, 'source': 'elasticsearch'})
        elif path == '/api/plans':
            respond(route, {'source': 'elasticsearch', 'plans': list(plans.values())})
        elif path.startswith('/api/plans/') and request.method == 'PUT':
            identifier = path.rsplit('/', 1)[1]
            updates.append(identifier)
            plans[identifier].update({**payload, 'talks': [records[i] for i in payload['talk_ids']]})
            respond(route, {**plans[identifier], 'source': 'elasticsearch'})
        elif path.startswith('/api/plans/'):
            respond(route, {**plans[path.rsplit('/', 1)[1]], 'source': 'elasticsearch'})
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
        expect(page.locator('.agenda-item')).to_have_count(0)
        expect(page.locator('.talk-card')).to_have_count(0)
        expect(page.locator('.agenda-save')).to_be_hidden()
        assert searches == [], 'Fresh planner must not load unrelated catalogue results'
        page.screenshot(path=str(OUTPUT / 'planner-first-fresh-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert page.locator('#build-button').bounding_box()['y'] < 600
        page.screenshot(path=str(OUTPUT / 'planner-first-fresh-mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})

        def build(text='kubernetes max 3', day='2026-11-10'):
            page.locator('#request-editor').evaluate('el => el.open = true')
            page.locator('#conference-day').select_option(day)
            page.locator('#interests').fill(text)
            page.locator('#build-button').click()

        build()
        expect(page.locator('.agenda-item')).to_have_count(2)
        expect(page.locator('.talk-card')).to_have_count(0)
        expect(page.locator('#day-source')).to_contain_text('Elasticsearch')
        expect(page.locator('#notice')).to_contain_text('Experience: beginner + intermediate')
        expect(page.locator('#request-editor')).not_to_have_attribute('open', '')
        assert page.locator('#plan-name').input_value(), 'Build needs a sensible editable default name'
        expect(page.locator('#save-plan-button')).to_be_visible()
        page.locator('#dismiss-notice').click()
        page.screenshot(path=str(OUTPUT / 'planner-first-built-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert page.locator('.agenda-item').first.bounding_box()['y'] < 844
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUTPUT / 'planner-first-built-mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('#plan-name').fill('My security day')
        page.locator('#save-plan-button').click()
        expect(page.locator('#notice')).to_contain_text('Your plan is saved in Elasticsearch')
        page.locator('#saved-library').evaluate('el => el.open = true')
        page.locator('[data-load-plan="test-plan"]').click()
        page.locator('#plan-name').fill('Edited day')
        page.locator('#save-plan-button').click()
        expect(page.locator('#plan-save-status')).to_contain_text('Edited day')
        assert plans['test-plan']['name'] == 'Edited day'
        earlier_ids = page.evaluate("localStorage.getItem('righttalk-agenda')")
        build('build a intermediate plan on kubernetes only', '2026-11-11')
        expect(page.locator('#latest-result-title')).to_have_text('No matching sessions · Nov 11')
        expect(page.locator('#latest-empty')).to_be_visible()
        expect(page.locator('#agenda-content')).to_be_hidden()
        expect(page.locator('.agenda-save')).to_be_hidden()
        expect(page.locator('.talk-card')).to_have_count(0)
        expect(page.locator('#day-source')).to_contain_text('0 talks')
        expect(page.locator('#retained-draft-note')).to_contain_text('Existing Nov 10 draft kept')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == earlier_ids
        page.screenshot(path=str(OUTPUT / 'planner-first-empty.png'), full_page=True)
        page.locator('#show-retained-draft').click()
        expect(page.locator('#plan-name')).to_have_value('Edited day')
        expect(page.locator('#save-plan-button')).to_have_text('Save changes')
        page.locator('#browse-program').click()
        expect(page.locator('.talk-card')).to_have_count(2)
        assert searches[-1]['day'] == ['2026-11-10']
        page.locator('#query').fill('next-day')
        page.locator('#search-form').evaluate('form => form.requestSubmit()')
        expect(page.locator('[data-add="next-day"]')).to_be_visible()
        page.locator('[data-add="next-day"]').click()
        expect(page.locator('#notice')).to_contain_text('This plan is for 2026-11-10')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == earlier_ids
        build('slow')
        assert 'build' in held
        page.locator('#clear-agenda').click()
        respond(held.pop('build'), built)
        expect(page.locator('#notice')).to_contain_text('Your current choices were kept')
        expect(page.locator('.agenda-item')).to_have_count(0)
        expect(page.locator('#save-plan-button')).to_have_text('Save plan')
        page.locator('#browse-program').click()
        expect(page.locator('.show-more')).to_be_visible()
        with page.expect_request(lambda request: '/api/search?' in request.url and 'offset=2' in request.url):
            page.locator('.show-more').click()
        page.locator('#query').fill('B')
        page.locator('#search-form').evaluate('form => form.requestSubmit()')
        expect(page.locator('.talk-card h3')).to_have_text(['Other programme talk'])
        respond(held.pop('page'), {**base_result, 'talks': [items[0]], 'total': 3})
        expect(page.locator('.talk-card')).to_have_count(1)
        for ids in (['missing'], ['a', 'next-day']):
            page.evaluate('(ids) => localStorage.setItem("righttalk-agenda", JSON.stringify(ids))', ids)
            page.reload()
            expect(page.locator('#agenda-status')).to_contain_text('Clash check unavailable')
            expect(page.locator('#clear-agenda')).to_be_enabled()
            page.locator('#clear-agenda').click()
            assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '[]'
        # A successful delayed first save establishes identity for ordinary edits.
        build()
        expect(page.locator('.agenda-item')).to_have_count(2)
        page.locator('#plan-name').fill('Delayed first save')
        page.locator('#save-plan-button').click()
        page.locator('[data-remove="b"]').click()
        page.locator('#plan-name').fill('Newer edits')
        expect(page.locator('#save-plan-button')).to_be_disabled()
        save_route, record = held.pop('save')
        plans[record['id']] = record
        respond(save_route, {**record, 'source': 'elasticsearch'})
        expect(page.locator('#save-plan-button')).to_have_text('Save changes')
        expect(page.locator('#plan-name')).to_have_value('Newer edits')
        expect(page.locator('#plan-save-status')).to_contain_text('Unsaved changes')
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == '["a"]'
        posts_before = post_count[0]
        page.locator('#save-plan-button').click()
        expect(page.locator('#notice')).to_contain_text('Saved plan updated')
        assert updates[-1] == record['id'] and post_count[0] == posts_before
        # Clear/new build creates a new context: a late save must not rebind it.
        page.locator('#clear-agenda').click()
        build()
        expect(page.locator('.agenda-item')).to_have_count(2)
        page.locator('#plan-name').fill('Delayed old draft')
        page.locator('#save-plan-button').click()
        old_route, old_record = held.pop('save')
        page.locator('#clear-agenda').click()
        build()
        expect(page.locator('.agenda-item')).to_have_count(2)
        plans[old_record['id']] = old_record
        respond(old_route, {**old_record, 'source': 'elasticsearch'})
        expect(page.locator('#notice')).to_contain_text('earlier draft was saved separately')
        expect(page.locator('#save-plan-button')).to_have_text('Save plan')
        assert page.locator('#plan-name').input_value() != 'Delayed old draft'
        posts_before = post_count[0]
        page.locator('#save-plan-button').click()
        expect(page.locator('#notice')).to_contain_text('Your plan is saved in Elasticsearch')
        assert post_count[0] == posts_before + 1
        help_button = page.get_by_role('button', name='How day planning works', exact=True)
        help_button.focus()
        expect(page.locator('#feature-tooltip')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#feature-tooltip')).to_be_hidden()
        help_button.click()
        expect(page.locator('#feature-tooltip')).to_be_visible()
        help_button.click()
        expect(page.locator('#feature-tooltip')).to_be_hidden()
        page.locator('#tab-venue').click()
        expect(page.locator('.place-card')).to_have_count(1)
        page.locator('#walking-budget').select_option('15')
        expect(page.locator('.place-card')).to_have_count(2)
        expect(page.locator('#venue-source')).to_contain_text('1200 m')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        browser.close()
    print('PASS: compact planner-first fresh/build, one timeline, inline save/open/edit, empty latest/retained draft, per-day browse, cross-day and async guards, walking budget, tooltips, mobile')


if __name__ == '__main__':
    main()
