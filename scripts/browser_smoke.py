"""Optional browser acceptance check. Requires Playwright and Chromium."""
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    output = Path(__file__).resolve().parent.parent / "artifacts"
    output.mkdir(exist_ok=True)
    base = os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")
    # These two clearly labeled demo samples are scheduled at the same time.
    clash_pair = (("talk-01", "Kubernetes Without the Jargon"),
                  ("talk-02", "Your First Threat Model"))
    with sync_playwright() as browser_tool:
        browser = browser_tool.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(120000)  # Cloud search latency varies with trial capacity.
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        if os.getenv('CHECK_OPENAI') != '1':
            page.locator('#smart-day').evaluate('node => node.checked = false')
        expect(page.locator(".talk-card")).to_have_count(24)
        expect(page.locator("#source")).to_have_text(re.compile(r"Elasticsearch · \d+ms · \d+ results"))
        assert page.locator(".talk-origin.official").count() > 0
        assert page.locator(".talk-origin.sample").count() > 0
        page.locator('#tab-venue').click()
        expect(page.locator("#venue-places")).to_have_attribute("aria-busy", "false")
        expect(page.locator("#venue-source")).to_contain_text("Elasticsearch geo search")
        page.locator('[data-place-category="eat"]').click()
        expect(page.locator("#venue-places .place-card")).to_have_count(4)
        assert page.locator("#venue-places a[href*='openstreetmap.org']").count() == 4
        page.locator('[data-place-category="coffee"]').click()
        expect(page.locator("#venue-places .place-card")).to_have_count(2)
        page.locator('#tab-day').click()
        assert page.locator("#track option").filter(has_text=re.compile(r"\(\d+\)")).count() > 0
        assert re.search(r"Captioned only \(\d+\)", page.locator("#captioned-count").inner_text())
        page.locator(".show-more").click()
        expect(page.locator(".talk-card")).to_have_count(48)
        page.locator("#interests").fill("getting started with kubernetes maximum 5 talks")
        with page.expect_response(lambda response: "/api/build-my-day" in response.url) as build_response:
            page.locator("#build-button").click()
        built_day = build_response.value.json()
        if os.getenv('CHECK_OPENAI') == '1':
            assert built_day['interpretation']['source'] == 'openai', built_day['interpretation']
            expect(page.locator('#day-interpretation')).to_contain_text('Interpreted by OpenAI')
        assert built_day["day"] == "2026-11-10" and 0 < len(built_day["talks"]) <= 5
        assert built_day['effective_level'] == 'beginner'
        assert all(talk['level'] == 'beginner' for talk in built_day['talks'])
        assert all(talk["start"].startswith("2026-11-10") for talk in built_day["talks"])
        expect(page.locator("#agenda-status")).to_contain_text("No clashes")
        expect(page.locator("#notice")).to_contain_text("maximum 5")
        expect(page.locator('#source')).to_contain_text(f"{len(built_day['talks'])} results")
        expect(page.locator('.talk-card')).to_have_count(len(built_day['talks']))
        expect(page.locator('#discover-title')).to_contain_text('Suggested talks')
        expect(page.locator('#browse-controls')).to_be_hidden()
        expect(page.locator('#day-source')).to_contain_text('Day builder · Elasticsearch')
        expect(page.locator('.agenda-time').first).to_contain_text('Nov 10')
        expect(page.locator(".agenda-item")).to_have_count(len(built_day['talks']))
        expect(page.locator(".reason").first).to_be_visible()
        saved_agenda = page.evaluate("localStorage.getItem('righttalk-agenda')")
        page.locator('.planning-options').evaluate('node => node.open = true')
        page.locator('#smart-day').uncheck()
        page.locator('#day-captioned').check()
        page.locator('#interests').fill('xyzzynonexistent')
        with page.expect_response(lambda response: '/api/build-my-day' in response.url):
            page.locator('#build-button').click()
        expect(page.locator('#notice')).to_contain_text('Your current agenda is unchanged')
        expect(page.locator('.talk-card')).to_have_count(0)
        expect(page.locator('#source')).to_contain_text('0 results')
        expect(page.locator('#retained-draft-note')).to_be_visible()
        page.locator('#day-captioned').uncheck()
        expect(page.locator('.agenda-item')).to_have_count(len(built_day['talks']))
        assert page.evaluate("localStorage.getItem('righttalk-agenda')") == saved_agenda
        page.locator('#plan-name').fill('Browser acceptance plan')
        with page.expect_response(lambda response: response.url.endswith('/api/plans') and response.request.method == 'POST') as saved_response:
            page.locator('#save-plan-button').click()
        assert saved_response.value.status == 200
        plan_id = saved_response.value.json()['id']
        expect(page.locator('#day-panel')).to_be_visible()
        expect(page.locator('#notice')).to_be_visible()
        expect(page.locator('#notice')).to_contain_text('Your plan is saved in Elasticsearch')
        page.locator('#saved-library').evaluate('node => node.open = true')
        expect(page.locator(f'[data-load-plan="{plan_id}"]')).to_be_visible()
        page.locator(f'[data-load-plan="{plan_id}"]').click()
        expect(page.locator('#day-panel')).to_be_visible()
        expect(page.locator('.agenda-item')).to_have_count(len(built_day['talks']))
        page.locator('#plan-name').fill('Updated acceptance plan')
        with page.expect_response(lambda response: response.url.endswith(f'/api/plans/{plan_id}') and response.request.method == 'PUT') as updated:
            page.locator('#save-plan-button').click()
        assert updated.value.status == 200
        expect(page.locator('#notice')).to_be_visible()
        expect(page.locator('#notice')).to_contain_text('Saved plan updated')
        page.locator('#saved-library').evaluate('node => node.open = true')
        expect(page.locator('.saved-plan').filter(has_text='Updated acceptance plan')).to_be_visible()
        page.once('dialog', lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response.url.endswith(f'/api/plans/{plan_id}') and response.request.method == 'DELETE') as deleted:
            page.locator(f'[data-delete-plan="{plan_id}"]').click()
        assert deleted.value.status == 200
        expect(page.locator(f'[data-load-plan="{plan_id}"]')).to_have_count(0)
        page.locator('#tab-day').click()
        page.reload()
        expect(page.locator("#agenda-status")).to_contain_text("No clashes")
        assert page.locator(".agenda-item").count() > 0, "Agenda did not persist"
        expect(page.locator('#draft-origin')).to_be_visible()
        page.locator("#clear-agenda").click()
        expect(page.locator(".agenda-item")).to_have_count(0)
        for index, (talk_id, title) in enumerate(clash_pair):
            page.locator("#query").fill(title)
            page.locator("#search-form").evaluate("form => form.requestSubmit()")
            card_button = page.locator(f'.talk-card [data-add="{talk_id}"]')
            expect(card_button).to_be_visible()
            card_button.click()
            expect(page.locator(".agenda-item")).to_have_count(index + 1)
        expect(page.locator("#agenda-status")).to_contain_text("clash to resolve")
        expect(page.locator(".alternative").first).to_be_visible()
        page.locator(".alternative").first.click()
        expect(page.locator("#agenda-status")).to_contain_text("No clashes")
        page.locator("#query").fill("observability")
        page.locator("#search-form").evaluate("form => form.requestSubmit()")
        expect(page.locator("#talks")).to_have_attribute("aria-busy", "false")
        expect(page.locator(".talk-card mark").first).to_be_visible()
        if os.getenv('CHECK_OPENAI') == '1':
            page.locator('#query').fill('beginer kubernets atmost 3 sessions')
            with page.expect_response(lambda response: '/api/search?' in response.url and 'smart=true' in response.url) as smart_response:
                page.locator('#smart-search').check()
            smart_data = smart_response.value.json()
            assert smart_data['interpretation']['source'] == 'openai'
            assert 0 < len(smart_data['talks']) <= 3
            expect(page.locator('#search-interpretation')).to_contain_text('Interpreted by OpenAI')
            page.locator('#query').fill('observability')
            page.locator('#smart-search').uncheck()
            expect(page.locator('#talks')).to_have_attribute('aria-busy', 'false')
        page.locator("#captioned").check()
        expect(page.locator("#talks")).to_have_attribute("aria-busy", "false")
        assert page.locator(".talk-card").count() > 0
        assert page.locator(".talk-card").filter(has_text="No captions").count() == 0
        check_cloud = os.getenv("CHECK_CLOUD_AI") == "1"
        if os.getenv("CHECK_LOCAL_AI") == "1" or check_cloud:
            # Explicit opt-in: this must exercise actual models, not a mocked
            # success or the correctly labelled keyword degradation path.
            page.locator("#reset-filters").click()
            expect(page.locator("#talks")).to_have_attribute("aria-busy", "false")
            assert page.locator(".talk-card").count() == 24
            page.locator("#query").fill("diagnose sluggish microservices")
            with page.expect_response(lambda response: "/api/search?" in response.url
                                      and "q=diagnose+sluggish+microservices" in response.url):
                page.locator("#search-form").evaluate("form => form.requestSubmit()")
            expect(page.locator("#search-method")).to_contain_text("Hybrid")
            expect(page.locator("#search-method")).not_to_have_class(re.compile('warning'))
            expect(page.locator(".talk-card").first).to_be_visible()
            page.locator("[data-explain]").first.click()
            if check_cloud:
                expect(page.locator(".explanation-label").first).to_contain_text("Session evidence", timeout=120000)
                assert "AI-generated" not in page.locator(".explanation-label").first.inner_text()
            else:
                expect(page.locator(".explanation-label").first).to_contain_text("AI-generated", timeout=120000)
            expect(page.locator(".match-explanation blockquote").first).to_be_visible()
            print("PASS: actual hybrid mode and " + ("extractive session evidence" if check_cloud else "local AI explanation with evidence"))
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        for tab in ('#tab-venue',):
            page.locator(tab).click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Mobile overflow in {tab}'
        page.locator('#tab-day').focus()
        page.keyboard.press('ArrowRight')
        expect(page.locator('#tab-venue')).to_be_focused()
        expect(page.locator('#venue-panel')).to_be_visible()
        assert not errors, errors
        browser.close()
    print("PASS: venue geo filters, facets/highlights, automatic search, captions, beginner day, inline plan library CRUD, empty results, agenda persistence, clash replacement, keyboard navigation, mobile layout")


if __name__ == "__main__":
    main()
