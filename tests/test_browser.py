"""Run against the real frontend and backend on ports 5173 and 8000."""
import os

from playwright.sync_api import expect, sync_playwright


def test_online_and_local():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        host = browser.new_page()
        host.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        sound = host.get_by_role("checkbox", name="Sound effects")
        sound.click()
        expect(sound).not_to_be_checked()
        host.get_by_role("button", name="Online", exact=True).click()
        host.get_by_label("red player name").fill("Nova")
        host.get_by_role("button", name="red owl").click()
        host.get_by_text("Create online room").click()
        expect(sound).to_be_hidden()
        settings = host.get_by_role("button", name="Game settings")
        settings.click()
        expect(sound).not_to_be_checked()
        sound.click()
        host.reload()
        host.get_by_text("Resume game").click()
        settings.click()
        expect(sound).to_be_checked()
        host.keyboard.press("Escape")
        expect(sound).to_be_hidden()
        invite = host.get_by_label("Invite link").input_value()
        guest = browser.new_page(viewport={"width": 390, "height": 844})
        guest.goto(invite)
        guest.get_by_label("guest player name").fill("Mika")
        guest.get_by_role("button", name="guest panda").click()
        guest.get_by_role("button", name="Join room").click()
        roll = host.get_by_role("button", name="Roll die")
        expect(roll).to_be_enabled()
        expect(guest.get_by_role("button", name="Roll die")).to_be_disabled()
        for page in (host, guest):
            assert page.locator("table.ludo-board td").count() == 225
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            board = page.locator("table.ludo-board").bounding_box()
            die = page.get_by_role("button", name="Roll die").bounding_box()
            assert abs(board["width"] - board["height"]) < 3
            assert die["y"] + die["height"] <= board["y"]
            expect(page.locator('.seat-card[data-seat="red"]')).to_contain_text("Nova")
            expect(page.locator('.seat-card[data-seat="yellow"]')).to_contain_text("Mika")
        roll.click()
        expect(host.locator(".tumble")).to_be_visible()
        expect(guest.get_by_text("Red rolled", exact=False)).to_be_visible()
        host.reload()
        host.get_by_text("Resume game").click()
        expect(host.get_by_text("Red rolled", exact=False)).to_be_visible()
        expect(host.get_by_text("Back to lobby")).to_have_count(0)
        settings.click()
        host.once("dialog", lambda dialog: dialog.accept())
        host.get_by_role("button", name="Leave game").click()
        host.get_by_role("button", name="One device").click()
        host.get_by_text("Pass and play").click()
        roll = host.get_by_role("button", name="Roll die")
        for _ in range(100):
            roll.click()
            host.wait_for_function("document.querySelector('.board-choice') || document.querySelector('.controls button:enabled')")
            if host.locator(".board-choice").count():
                break
        host.locator(".board-choice").first.click()
        expect(host.get_by_text("moved pawn", exact=False)).to_be_visible()
        browser.close()


def test_side_docks_on_phone():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        for count in (3, 4):
            page = browser.new_page(viewport={"width": 375, "height": 812})
            page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
            page.get_by_role("button", name=str(count), exact=True).click()
            page.get_by_text("Pass and play").click()
            expect(page.locator(".seat-card")).to_have_count(count)
            board = page.locator(".board-frame").bounding_box()
            green = page.locator(".seat-card[data-seat=green]").bounding_box()
            assert green["x"] >= board["x"] + board["width"] - 1
            if count == 4:
                blue = page.locator(".seat-card[data-seat=blue]").bounding_box()
                assert blue["x"] + blue["width"] <= board["x"] + 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()

def test_two_player_match_fits_resized_viewport():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        page.get_by_text("Pass and play").click()
        expect(page.locator(".seat-card")).to_have_count(2)
        for width, height in [(1440, 800), (1280, 640), (390, 660), (844, 390)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
            for element in page.locator(".board-frame, .seat-card, .roll").all():
                box = element.bounding_box()
                assert 0 <= box["y"] and box["y"] + box["height"] <= height
        browser.close()


def test_missing_saved_room_returns_to_lobby_without_polling():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        page.add_init_script("""localStorage.setItem('ludo-seat',
            JSON.stringify({room: 'missing-room', token: 'old-seat'}))""")
        requests = []
        def missing(route):
            requests.append(route.request.url)
            route.fulfill(status=404, json={"detail": "Room not found."})
        page.route("**/rooms/missing-room*", missing)
        page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        expect(page.get_by_role("alert")).to_have_text("Room not found.")
        expect(page.get_by_text("Pass and play")).to_be_visible()
        assert page.evaluate("localStorage.getItem('ludo-seat')") is None
        page.wait_for_timeout(2200)
        assert len(requests) == 1
        browser.close()
