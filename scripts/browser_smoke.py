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
        expect(page.locator(".talk-card")).to_have_count(24)
        expect(page.locator("#source")).to_have_text(re.compile(r"Elasticsearch · \d+ms · \d+ results"))
        assert page.locator(".talk-origin.official").count() > 0
        assert page.locator(".talk-origin.sample").count() > 0
        expect(page.locator("#venue-places")).to_have_attribute("aria-busy", "false")
        expect(page.locator("#venue-source")).to_contain_text("Elasticsearch geo search")
        page.locator('[data-place-category="eat"]').click()
        expect(page.locator("#venue-places .place-card")).to_have_count(4)
        assert page.locator("#venue-places a[href*='openstreetmap.org']").count() == 4
        page.locator('[data-place-category="coffee"]').click()
        expect(page.locator("#venue-places .place-card")).to_have_count(2)
        assert page.locator("#track option").filter(has_text=re.compile(r"\(\d+\)")).count() > 0
        assert re.search(r"Captioned only \(\d+\)", page.locator("#captioned-count").inner_text())
        page.locator(".show-more").click()
        expect(page.locator(".talk-card")).to_have_count(48)
        page.locator("#interests").fill("getting started with kubernetes maximum 5 talks")
        with page.expect_response(lambda response: "/api/build-my-day" in response.url) as build_response:
            page.locator("#build-button").click()
        built_day = build_response.value.json()
        assert built_day["day"] == "2026-11-10" and len(built_day["talks"]) == 5
        assert all(talk["start"].startswith("2026-11-10") for talk in built_day["talks"])
        expect(page.locator("#agenda-status")).to_contain_text("No clashes")
        expect(page.locator("#notice")).to_contain_text("maximum 5")
        expect(page.locator(".agenda-item")).to_have_count(5)
        expect(page.locator(".reason").first).to_be_visible()
        page.reload()
        expect(page.locator("#agenda-status")).to_contain_text("No clashes")
        assert page.locator(".agenda-item").count() > 0, "Agenda did not persist"
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
            page.locator("#search-mode").select_option("hybrid")
            page.locator("#query").fill("find why requests are sluggish")
            with page.expect_response(lambda response: "/api/search?" in response.url
                                      and "q=find+why+requests+are+sluggish" in response.url):
                page.locator("#search-form").evaluate("form => form.requestSubmit()")
            expect(page.locator("#search-method")).to_contain_text("Hybrid")
            expect(page.locator("#search-mode-note")).to_be_hidden()
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
        assert not errors, errors
        browser.close()
    print("PASS: venue geo filters, live facets/highlights, search, captions, day builder, saved agenda, clash replacement, mobile layout")


if __name__ == "__main__":
    main()
