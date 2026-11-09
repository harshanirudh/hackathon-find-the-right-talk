"""Live planner-first browser acceptance; opt in to OpenAI/semantic assertions."""
import os
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright


def main():
    output = Path(__file__).resolve().parents[1] / 'artifacts'
    output.mkdir(exist_ok=True)
    base = os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/')
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium')
        page = browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(90000)
        errors, created_ids = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base)
        expect(page.locator('.agenda-item')).to_have_count(0)
        expect(page.locator('.talk-card')).to_have_count(0)
        if os.getenv('CHECK_OPENAI') != '1':
            page.locator('#smart-day').evaluate('el => el.checked = false')
        page.screenshot(path=str(output / 'planner-first-live-fresh-desktop.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert page.locator('#build-button').bounding_box()['y'] < 650
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output / 'planner-first-live-fresh-mobile.png'), full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        try:
            page.locator('#interests').fill('getting started with kubernetes maximum 5 talks')
            with page.expect_response(lambda response: '/api/build-my-day' in response.url) as response:
                page.locator('#build-button').click()
            built = response.value.json()
            assert built['source'] == 'elasticsearch' and 0 < len(built['talks']) <= 5
            assert built['day'] == '2026-11-10' and all(t['level'] == 'beginner' for t in built['talks'])
            if os.getenv('CHECK_OPENAI') == '1':
                assert built['interpretation']['source'] == 'openai', built['interpretation']
            count = len(built['talks'])
            expect(page.locator('.agenda-item')).to_have_count(count)
            expect(page.locator('.talk-card')).to_have_count(0)
            expect(page.locator('#agenda-status')).to_contain_text('No clashes')
            expect(page.locator('#day-source')).to_contain_text('Elasticsearch')
            assert page.locator('#plan-name').input_value()
            page.locator('#dismiss-notice').click()
            page.screenshot(path=str(output / 'planner-first-live-built-desktop.png'), full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert page.locator('.agenda-item').first.bounding_box()['y'] < 1000
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / 'planner-first-live-built-mobile.png'), full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('.agenda-item .session-details').first.evaluate('el => el.open = true')
            assert float(page.locator('.agenda-item .talk-description').first.evaluate('el => getComputedStyle(el).fontSize').rstrip('px')) >= 13
            page.locator('#plan-name').fill('Browser acceptance plan')
            with page.expect_response(lambda response: response.url.endswith('/api/plans') and response.request.method == 'POST') as saved:
                page.locator('#save-plan-button').click()
            assert saved.value.status == 200
            plan_id = saved.value.json()['id']; created_ids.append(plan_id)
            expect(page.locator('#notice')).to_contain_text('Your plan is saved in Elasticsearch')
            page.locator('#saved-library').evaluate('el => el.open = true')
            page.locator(f'[data-load-plan="{plan_id}"]').click()
            page.locator('#plan-name').fill('Updated acceptance plan')
            with page.expect_response(lambda response: response.url.endswith(f'/api/plans/{plan_id}') and response.request.method == 'PUT') as updated:
                page.locator('#save-plan-button').click()
            assert updated.value.status == 200
            expect(page.locator('#plan-save-status')).to_contain_text('Updated acceptance plan')
            earlier_ids = page.evaluate("localStorage.getItem('righttalk-agenda')")
            page.locator('#request-editor').evaluate('el => el.open = true')
            page.locator('#smart-day').evaluate('el => el.checked = false')
            page.locator('#conference-day').select_option('2026-11-11')
            page.locator('#day-captioned').check()
            page.locator('#interests').fill('xyzzynonexistent')
            page.locator('#build-button').click()
            expect(page.locator('#latest-result-title')).to_contain_text('Nov 11')
            expect(page.locator('#latest-empty')).to_be_visible()
            expect(page.locator('#agenda-content')).to_be_hidden()
            expect(page.locator('.talk-card')).to_have_count(0)
            expect(page.locator('#retained-draft-note')).to_contain_text('Existing Nov 10 draft kept')
            assert page.evaluate("localStorage.getItem('righttalk-agenda')") == earlier_ids
            page.screenshot(path=str(output / 'planner-first-live-empty.png'), full_page=True)
            page.locator('#show-retained-draft').click()
            expect(page.locator('#plan-name')).to_have_value('Updated acceptance plan')
            page.locator('#browse-program').click()
            expect(page.locator('#discovery-context')).to_contain_text('retained Nov 10')
            expect(page.locator('.talk-card')).to_have_count(24)
            expect(page.locator('#source')).to_contain_text('Elasticsearch')
            assert page.locator('#track option').filter(has_text=re.compile(r'\(\d+\)')).count() > 0
            page.locator('.show-more').click()
            expect(page.locator('.talk-card')).to_have_count(48)
            page.locator('#saved-library').evaluate('el => el.open = true')
            page.once('dialog', lambda dialog: dialog.accept())
            with page.expect_response(lambda response: response.url.endswith(f'/api/plans/{plan_id}') and response.request.method == 'DELETE') as deleted:
                page.locator(f'[data-delete-plan="{plan_id}"]').click()
            assert deleted.value.status == 200; created_ids.remove(plan_id)
            page.reload()
            expect(page.locator('#draft-origin')).to_be_visible()
            expect(page.locator('.agenda-item')).to_have_count(count)
            page.locator('#clear-agenda').click()
            expect(page.locator('.agenda-item')).to_have_count(0)
            page.locator('#conference-day').select_option('2026-11-09')
            page.locator('#browse-program').click()
            for talk_id, title in (('talk-01','Kubernetes Without the Jargon'),('talk-02','Your First Threat Model')):
                page.locator('#query').fill(title)
                page.locator('#search-form').evaluate('form => form.requestSubmit()')
                page.locator(f'[data-add="{talk_id}"]').click()
            expect(page.locator('#agenda-status')).to_contain_text('clash to resolve')
            page.locator('.alternative').first.click()
            expect(page.locator('#agenda-status')).to_contain_text('No clashes')
            page.locator('#query').fill('observability')
            page.locator('#search-form').evaluate('form => form.requestSubmit()')
            expect(page.locator('#talks')).to_have_attribute('aria-busy','false')
            expect(page.locator('.talk-card mark').first).to_be_visible()
            page.locator('#captioned').check()
            expect(page.locator('#talks')).to_have_attribute('aria-busy','false')
            assert page.locator('.talk-card').count() > 0
            if os.getenv('CHECK_CLOUD_AI') == '1' or os.getenv('CHECK_LOCAL_AI') == '1':
                page.locator('#reset-filters').click()
                page.locator('#query').fill('diagnose sluggish microservices')
                page.locator('#search-form').evaluate('form => form.requestSubmit()')
                expect(page.locator('#search-method')).to_contain_text('Hybrid')
                page.locator('.talk-card .session-details').first.evaluate('el => el.open = true')
                page.locator('.talk-card [data-explain]').first.click()
                expect(page.locator('.talk-card .explanation-label').first).to_contain_text('Session evidence' if os.getenv('CHECK_CLOUD_AI') == '1' else 'AI-generated')
            page.locator('#tab-venue').click()
            expect(page.locator('#venue-places')).to_have_attribute('aria-busy','false')
            expect(page.locator('#venue-source')).to_contain_text('Elasticsearch geo search')
            expect(page.locator('#venue-title')).to_have_text('Near the demo venue')
            page.locator('#walking-budget').select_option('5')
            expect(page.locator('#venue-source')).to_contain_text('400 m')
            page.locator('#walking-budget').select_option('15')
            expect(page.locator('#venue-source')).to_contain_text('1200 m')
            page.locator('[data-place-category="eat"]').click()
            expect(page.locator('#venue-places')).to_have_attribute('aria-busy','false')
            assert page.locator('.place-card').count() > 0
            page.screenshot(path=str(output / 'planner-first-live-nearby.png'), full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#tab-day').focus(); page.keyboard.press('ArrowRight')
            expect(page.locator('#tab-venue')).to_be_focused()
            assert not errors, errors
        finally:
            key = page.evaluate("localStorage.getItem('righttalk-planner-key')")
            for identifier in created_ids:
                page.request.delete(f'{base}/api/plans/{identifier}', headers={'X-Planner-Key':key})
            browser.close()
    print('PASS: live compact planner, one timeline, inline plan CRUD, empty/retained draft, per-day browse, facets/highlights, clashes, walking budget, mobile')


if __name__ == '__main__':
    main()
