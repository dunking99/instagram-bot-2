#!/usr/bin/env python3
"""
One-time setup: pass data18's age gate by hand and save the resulting cookie.

  .venv/bin/python setup_session.py

A browser window opens on data18.com. Click "I AGREE" (and solve anything it asks you).
As soon as a performer page loads with videos on it, the cookies are saved to data/session.json and the window closes.
Run it again whenever the scraper says the session has expired.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).parent / "data" / "session.json"
TEST_PAGE = "https://www.data18.com/name/kyler-quinn"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for you to finish (default 180)")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1100, "height": 850})
        page = context.new_page()
        page.goto(TEST_PAGE)
        print('Click "I AGREE" in the browser window (and solve anything it asks)...')
        deadline = time.time() + args.timeout
        ok = False
        while time.time() < deadline:
            try:
                if page.url.rstrip("/").endswith("/name/kyler-quinn") and page.query_selector('div[id^="item"]'):
                    ok = True
                    break
                if "/sys/" in page.url or "captcha" in page.url:
                    pass  # still on the gate, keep waiting
                elif "/name/" not in page.url:
                    page.goto(TEST_PAGE)  # gate passed but landed elsewhere: go back to the test page
            except Exception:
                pass
            page.wait_for_timeout(1000)
        if not ok:
            print("Timed out before a performer page loaded. Nothing saved.")
            browser.close()
            return 1
        cookies = [c for c in context.cookies() if "data18" in c["domain"]]
        user_agent = page.evaluate("navigator.userAgent")
        SESSION_FILE.parent.mkdir(exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"user_agent": user_agent, "cookies": cookies}, indent=2))
        browser.close()
    print(f"Saved {len(cookies)} cookies to {SESSION_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
