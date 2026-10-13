"""
Show which Instagram account auth.json is logged in as.

Run:
    python3 whoami.py

Loads the saved session headlessly, opens instagram.com once, and reads your
username from the profile picture in the navigation ("<username>'s profile picture").
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

AUTH_FILE = Path(__file__).with_name("auth.json")


def main() -> int:
    if not AUTH_FILE.exists():
        print("auth.json not found. Run `python3 login.py` first.", file=sys.stderr)
        return 1

    # The numeric account ID is stored in the cookies, so we can show it even offline.
    cookies = json.loads(AUTH_FILE.read_text()).get("cookies", [])
    user_id = next((c["value"] for c in cookies if c["name"] == "ds_user_id"), None)
    if not any(c["name"] == "sessionid" and c["value"] for c in cookies):
        print("auth.json has no logged-in session. Run `python3 login.py`.", file=sys.stderr)
        return 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_context(storage_state=str(AUTH_FILE)).new_page()
                page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(4000)
                if "/accounts/login" in page.url:
                    print("Session expired. Run `python3 login.py` again.", file=sys.stderr)
                    return 1
                alts = page.eval_on_selector_all(
                    "img[alt$=\"'s profile picture\"]", "els => els.map(e => e.alt)")
                names = [m.group(1) for a in alts if (m := re.match(r"(.+)'s profile picture$", a))]
                if names:
                    print(f"Logged in as: {names[0]}  (account ID {user_id})")
                else:
                    print(f"Session is valid (account ID {user_id}) but I couldn't read the "
                          f"username from the page. Layout may have changed.")
                return 0
            finally:
                browser.close()
    except PlaywrightError as e:
        print(f"Browser error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
