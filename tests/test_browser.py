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
        saved = host.get_by_role("region", name="Saved game")
        expect(saved).to_contain_text("Nova")
        expect(saved).to_contain_text("Waiting for players")
        host.get_by_role("button", name="One device").click()
        expect(saved).to_be_hidden()
        host.get_by_role("button", name="Online", exact=True).click()
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
            expect(page.locator('.dice-dock[data-seat="red"] .roll-timer .turn-timer')).to_be_visible()
            expect(page.locator(".presence")).to_have_count(0)
        for page in (host, guest):
            expect(page.get_by_role("img", name="Ludo board")).to_be_visible()
            assert page.locator(".ludo-board .pawn-icon").count() == 8
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            board = page.locator(".ludo-board").bounding_box()
            die = page.get_by_role("button", name="Roll die").bounding_box()
            assert abs(board["width"] - board["height"]) < 3
            assert die["y"] + die["height"] <= board["y"]
            expect(page.locator('.seat-card[data-seat="red"]')).to_contain_text("Nova")
            expect(page.locator('.seat-card[data-seat="yellow"]')).to_contain_text("Mika")
        pending_roll = []
        host.route("**/actions", lambda route: pending_roll.append(route))
        roll.click()
        expect(host.locator(".tumble")).to_be_visible()
        expect(roll).to_be_disabled()
        pending_roll.pop().continue_()
        host.unroute("**/actions")
        expect(guest.get_by_text("Red rolled", exact=False)).to_be_visible()
        host.reload()
        expect(saved).to_contain_text("Started")
        expect(saved).to_contain_text("Mika")
        host.get_by_text("Resume game").click()
        expect(host.get_by_text("Red rolled", exact=False)).to_be_visible()
        expect(host.get_by_text("Back to lobby")).to_have_count(0)
        settings.click()
        host.once("dialog", lambda dialog: dialog.accept())
        host.get_by_role("button", name="Leave game").click()
        # Leaving on purpose hands the seat to a computer, since substitutes are on by default.
        expect(guest.locator('.seat-card[data-seat="red"] .presence')).to_have_text("CPU")
        expect(host.get_by_role("alert")).to_have_text("You left the game.")
        expect(host.get_by_text("Resume game")).to_have_count(0)
        host.get_by_role("button", name="One device").click()
        host.get_by_text("Pass and play").click()
        roll = host.get_by_role("button", name="Roll die")
        for _ in range(100):
            roll.click()
            expect(host.locator(".board-choice, .controls button:enabled").first).to_be_attached()
            if host.locator(".board-choice").count():
                break
        host.locator(".board-choice").first.click()
        traveler = host.locator(".traveling-pawn")
        expect(traveler).to_be_visible()
        expect(roll).to_be_disabled()
        expect(traveler).to_be_hidden()
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
        # Development StrictMode may run the saved-game check twice; no polling follows.
        checked = len(requests)
        assert checked <= 2
        page.wait_for_timeout(2200)
        assert len(requests) == checked
        browser.close()


def test_automatic_move_holds_result_at_rollers_seat():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        page.get_by_text("Pass and play").click()
        roll = page.get_by_role("button", name="Roll die")
        expect(roll).to_be_enabled()
        # Give red one pawn on the track and fix the roll for a predictable handoff.
        room = page.evaluate("JSON.parse(localStorage.getItem('ludo-seat')).room")
        def snapshot(route):
            state = route.fetch().json()
            state["pawns"][0].update(row=6, col=1, step=0)
            route.fulfill(json=state)
        page.route("**/rooms/" + room + "*", snapshot)
        page.reload()
        page.get_by_text("Resume game").click()
        expect(roll).to_be_enabled()
        def auto_move(route):
            state = page.request.get(route.request.url.removesuffix("/actions"),
                                     headers={"Authorization": route.request.headers["authorization"]}).json()
            state.update(revision=state["revision"]+1, roll_number=1, die=3, roller="red", current="yellow",
                         last_move={"roll": 1, "pawn": "red-1", "path": [[6, i] for i in range(1, 5)]})
            state["pawns"][0].update(row=6, col=4, step=3)
            route.fulfill(json=state)
        page.route("**/actions", auto_move)
        roll.click()
        expect(page.locator(".rest .cube[data-value=\"3\"]")).to_have_count(1)
        dock = page.locator(".dice-dock")
        expect(dock).to_have_attribute("data-seat", "red")
        pawn = page.locator(".traveling-pawn")
        assert pawn.evaluate("(p) => p.getAnimations()[0].effect.getComputedTiming().progress") == 0
        expect(roll).to_be_disabled()
        expect(dock).to_have_attribute("data-seat", "yellow")
        expect(pawn).to_have_count(0)
        browser.close()


def test_own_invite_link_keeps_host_seat():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        page.get_by_role("button", name="Online", exact=True).click()
        page.get_by_text("Create online room").click()
        invite = page.get_by_label("Invite link").input_value()
        seat = page.evaluate("localStorage.getItem('ludo-seat')")
        page.goto(invite)
        expect(page.get_by_text("Resume game")).to_be_visible()
        page.get_by_role("button", name="Join room").click()
        expect(page.get_by_role("alert")).to_have_text("You already have a seat in this room. Use Resume game.")
        assert page.evaluate("localStorage.getItem('ludo-seat')") == seat
        browser.close()


def test_leaving_without_substitutes_removes_pawns():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        host = browser.new_page()
        host.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        host.get_by_role("button", name="Online", exact=True).click()
        host.get_by_role("button", name="3", exact=True).click()
        host.get_by_role("checkbox", name="Computer substitutes", exact=False).uncheck()
        host.get_by_text("Create online room").click()
        invite = host.get_by_label("Invite link").input_value()
        guests = []
        for _ in range(2):
            guest = browser.new_page()
            guest.goto(invite)
            guest.get_by_role("button", name="Join room").click()
            guests.append(guest)
        expect(host.locator('.pawn-icon[aria-label="green pawn"]')).to_have_count(4)
        green = guests[0]
        green.get_by_role("button", name="Game settings").click()
        green.once("dialog", lambda dialog: dialog.accept())
        green.get_by_role("button", name="Leave game").click()
        expect(green.get_by_role("alert")).to_have_text("You left the game.")
        expect(host.locator('.seat-card[data-seat="green"] .presence')).to_have_text("Left")
        expect(host.locator('.pawn-icon[aria-label="green pawn"]')).to_have_count(0)
        browser.close()


def test_menu_pages_and_deep_links():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        base = os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173")
        page.goto(base)
        nav = page.get_by_role("navigation", name="Main")
        nav.get_by_role("link", name="How to play").click()
        expect(page).to_have_url(base + "/rules")
        expect(page.get_by_role("heading", name="How to play")).to_be_visible()
        nav.get_by_role("link", name="About").click()
        expect(page.get_by_role("heading", name="Privacy")).to_be_visible()
        page.go_back()
        expect(page.get_by_role("heading", name="How to play")).to_be_visible()
        page.goto(base + "/about")
        expect(page.get_by_role("heading", name="About", exact=True)).to_be_visible()
        nav.get_by_role("link", name="Play", exact=True).click()
        expect(page.get_by_text("Pass and play")).to_be_visible()
        for width in (375, 1280):
            page.set_viewport_size({"width": width, "height": 800})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


def emailed_code(address, after):
    """Read the newest code sent to an address from the API's development mail folder."""
    import glob, json, time
    folder = os.getenv("LUDO_MAIL_DIR", "/tmp/ludo-mail")
    for _ in range(50):
        for path in sorted(glob.glob(folder + "/*.json"), reverse=True):
            message = json.load(open(path))
            if message["to"] == address and message["code"] and os.path.getmtime(path) >= after:
                return message["code"]
        time.sleep(0.2)
    raise AssertionError("No code emailed to " + address)


def test_account_resumes_online_game_on_another_device():
    import secrets, time
    username = "e2e_" + secrets.token_hex(4)
    email = username + "@example.com"
    base = os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        laptop = browser.new_page()
        laptop.goto(base + "/account")
        laptop.get_by_role("button", name="Create account").first.click()
        laptop.get_by_label("Username").fill(username)
        laptop.get_by_label("Email").fill(email)
        laptop.get_by_label("Password", exact=True).fill("a long password")
        laptop.get_by_label("Confirm password").fill("a long password")
        started = time.time() - 1
        laptop.locator("form").get_by_role("button", name="Create account").click()
        expect(laptop.get_by_role("heading", name="Check your email")).to_be_visible()
        expect(laptop.get_by_role("button", name="Resend code in", exact=False)).to_be_disabled()
        laptop.get_by_label("6-digit code").fill(emailed_code(email, started))
        laptop.get_by_role("button", name="Verify email").click()
        expect(laptop.get_by_role("heading", name="Hi, " + username)).to_be_visible()
        laptop.get_by_label("Display name").fill("Nova")
        laptop.get_by_role("button", name="owl").click()
        laptop.get_by_role("button", name="Save profile").click()
        expect(laptop.get_by_role("status")).to_have_text("Saved.")
        laptop.get_by_role("navigation", name="Main").get_by_role("link", name="Play", exact=True).click()
        laptop.get_by_role("button", name="Online", exact=True).click()
        expect(laptop.get_by_label("red player name")).to_have_value("Nova")
        laptop.get_by_text("Create online room").click()
        expect(laptop.get_by_label("Invite link")).to_be_visible()
        # On a second device the player has forgotten the password and resets it by email.
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.goto(base + "/account")
        phone.get_by_label("Username or email").fill(email)
        phone.get_by_label("Password", exact=True).fill("wrong password")
        phone.locator("form").get_by_role("button", name="Sign in").click()
        expect(phone.get_by_role("alert")).to_have_text("Wrong username, email or password.")
        phone.get_by_role("button", name="Forgot password?").click()
        phone.get_by_label("Email").fill(email)
        started = time.time() - 1
        phone.get_by_role("button", name="Send code").click()
        expect(phone.get_by_role("heading", name="Choose a new password")).to_be_visible()
        phone.get_by_label("6-digit code").fill(emailed_code(email, started))
        phone.get_by_label("New password").fill("another long one")
        phone.get_by_label("Confirm password").fill("another long one")
        phone.get_by_role("button", name="Set password and sign in").click()
        expect(phone.get_by_role("navigation", name="Main")).to_contain_text(username)
        # The same account takes the online seat over on this device.
        phone.get_by_role("navigation", name="Main").get_by_role("link", name="Play", exact=True).click()
        phone.get_by_role("button", name="Online", exact=True).click()
        games = phone.get_by_role("region", name="Your online games")
        expect(games).to_contain_text("Nova")
        games.get_by_role("button", name="Resume").click()
        expect(phone.get_by_label("Invite link")).to_be_visible()
        expect(phone.locator('.seat-card[data-seat="red"]')).to_contain_text("Nova")
        # The first device's seat stops working and it returns to the lobby.
        expect(laptop.get_by_role("alert")).to_have_text("This seat belongs to another session.", timeout=8000)
        browser.close()


def test_victory_shows_confetti_and_lobby_button():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page()
        page.goto(os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173"))
        page.get_by_text("Pass and play").click()
        roll = page.get_by_role("button", name="Roll die")
        expect(roll).to_be_enabled()
        room = page.evaluate("JSON.parse(localStorage.getItem('ludo-seat')).room")
        def won(route):
            state = route.fetch().json()
            state.update(phase="won", current="yellow", revision=state["revision"] + 1, message="Yellow wins!")
            route.fulfill(json=state)
        page.route("**/rooms/" + room + "*", won)
        victory = page.locator(".victory")
        expect(victory).to_contain_text("Yellow wins!")
        expect(page.locator("canvas.confetti")).to_have_count(1)
        victory.get_by_role("button", name="Back to lobby").click()
        expect(page.get_by_text("Pass and play")).to_be_visible()
        browser.close()


def test_chat_emotes_limits_and_muting():
    base = os.getenv("LUDO_FRONTEND_URL", "http://localhost:5173")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        host = browser.new_page(viewport={"width": 1280, "height": 800})
        host.goto(base)
        host.get_by_role("button", name="Online", exact=True).click()
        host.get_by_label("red player name").fill("Nova")
        host.get_by_text("Create online room").click()
        invite = host.get_by_label("Invite link").input_value()
        guest = browser.new_page(viewport={"width": 390, "height": 844})
        guest.goto(invite)
        guest.get_by_label("guest player name").fill("Mika")
        guest.get_by_role("button", name="Join room").click()
        expect(guest.get_by_role("button", name="Roll die")).to_be_visible()
        # Wide screens show the chat beside the board; phones get a button and a sheet.
        host_log = host.get_by_role("log", name="Messages")
        expect(host_log).to_be_visible()
        expect(guest.get_by_role("log", name="Messages")).to_be_hidden()
        # Messages typed back to back all arrive, even while the previous one is still sending.
        for line in ("hello there", "second", "third"):
            host.get_by_role("textbox", name="Message").fill(line)
            host.get_by_role("textbox", name="Message").press("Enter")
        expect(host_log).to_contain_text("You hello there")
        expect(host_log).to_contain_text("You third")
        expect(host_log).to_contain_text("You second")
        expect(guest.get_by_role("button", name="Open chat, 3 new")).to_be_visible()
        guest.get_by_role("button", name="Open chat, 3 new").click()
        guest_log = guest.get_by_role("log", name="Messages")
        expect(guest_log).to_contain_text("Nova hello there")
        assert guest.evaluate("document.documentElement.scrollWidth <= innerWidth")
        guest.get_by_role("button", name="Good luck!").first.click()
        expect(host_log).to_contain_text("Mika Good luck!")
        guest.keyboard.press("Escape")
        expect(guest_log).to_be_hidden()
        # Tap a player's picture to throw an emote at them; it flies across the other screen too.
        guest.get_by_role("button", name="Send an emote to Nova").click()
        guest.get_by_role("dialog", name="Send an emote to Nova").get_by_role("button", name="Snake").click()
        expect(host.locator(".emote-flight")).to_have_count(1)
        expect(host_log).to_contain_text("Mika sent a sneaky snake to You 🐍")
        # Three emotes, then the allowance runs out for a while.
        guest.get_by_role("button", name="Send a reaction").click()
        guest.get_by_role("dialog", name="Send a reaction").get_by_role("button", name="Oooo!").click()
        guest.get_by_role("button", name="Send a reaction").click()
        picker = guest.get_by_role("dialog", name="Send a reaction")
        picker.get_by_role("button", name="Haha!").click()
        guest.get_by_role("button", name="Send a reaction").click()
        expect(picker).to_contain_text("More emotes in")
        expect(picker.get_by_role("button", name="Haha!")).to_be_disabled()
        guest.keyboard.press("Escape")
        # Muting a player hides their messages.
        host.get_by_role("button", name="Chat settings").click()
        host.get_by_role("checkbox", name="Mute Mika").check()
        guest.get_by_role("button", name="Open chat").click()
        guest.get_by_role("textbox", name="Message").fill("secret")
        guest.get_by_role("button", name="Send", exact=True).click()
        expect(guest.get_by_role("log", name="Messages")).to_contain_text("You secret")
        host.wait_for_timeout(2500)
        expect(host_log).not_to_contain_text("secret")
        host.get_by_role("checkbox", name="Mute Mika").uncheck()
        expect(host_log).to_contain_text("Mika secret")
        # The desktop panel collapses to a button.
        host.get_by_role("button", name="Close chat").first.click()
        expect(host_log).to_be_hidden()
        host.get_by_role("button", name="Open chat").click()
        expect(host_log).to_be_visible()
        browser.close()
