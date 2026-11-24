"""Run against the real frontend and backend on ports 5173 and 8000."""
import os

from playwright.sync_api import expect, sync_playwright


def test_online_and_local():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        host = browser.new_page()
        host.goto("http://localhost:5173")
        host.get_by_text("Create online room").click()
        invite = host.get_by_label("Invite link").input_value()
        guest = browser.new_page()
        guest.goto(invite)
        guest.get_by_role("button", name="Join room").click()
        roll = host.get_by_role("button", name="Roll die")
        expect(roll).to_be_enabled()
        expect(guest.get_by_role("button", name="Roll die")).to_be_disabled()
        roll.click()
        expect(guest.get_by_text("Red rolled", exact=False)).to_be_visible()
        host.reload()
        expect(host.get_by_text("Red rolled", exact=False)).to_be_visible()
        host.get_by_text("Back to lobby").click()
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
