"""
STEP 1 - Session initialization (run once, or whenever your session expires).

Opens a visible browser at instagram.com so you can log in by hand (username,
password, 2FA). As soon as a logged-in session cookie appears, the authenticated
state (cookies + localStorage) is saved to auth.json.

Setup:
    pip install playwright
    playwright install chromium

Run:
    python login.py              # waits up to 60 seconds for you to log in
    python login.py --timeout 180
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

AUTH_FILE = Path(__file__).with_name("auth.json")


def is_logged_in(context) -> bool:
    """Instagram sets a 'sessionid' cookie only for authenticated sessions."""
    return any(c["name"] == "sessionid" and c["value"] for c in context.cookies())


def main() -> int:
    parser = argparse.ArgumentParser(description="Log in to Instagram and save auth.json")
    parser.add_argument("--timeout", type=int, default=60,
                        help="seconds to wait for you to finish logging in (default: 60)")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        try:
            page.goto("https://www.instagram.com/accounts/login/", timeout=30_000)
            print(f"Log in in the browser window (including 2FA). Waiting up to {args.timeout}s...")

            # Poll so we finish early once login completes, instead of always sleeping.
            for _ in range(args.timeout):
                if is_logged_in(context):
                    page.wait_for_timeout(3000)  # let post-login tokens settle
                    # Instagram may show a cookie-choice page; saving before it is cleared gives a
                    # session that gets redirected there. Open the home page and wait for the user.
                    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    if "/consent" in page.url:
                        print("Instagram is asking about cookies. Choose an option in the browser window...")
                    for _ in range(args.timeout):
                        if "/consent" not in page.url and "/accounts/login" not in page.url:
                            break
                        page.wait_for_timeout(1000)
                    else:
                        print("Still on the cookie/login page. Re-run and choose an option.", file=sys.stderr)
                        return 1
                    page.wait_for_timeout(1500)
                    break
                page.wait_for_timeout(1000)
            else:
                print("Timed out: no logged-in session detected. Re-run, optionally "
                      "with a larger --timeout.", file=sys.stderr)
                return 1

            context.storage_state(path=str(AUTH_FILE))
            print(f"Saved session to {AUTH_FILE}")
            return 0
        except PlaywrightError as e:
            print(f"Browser error (window closed or network problem): {e}", file=sys.stderr)
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
