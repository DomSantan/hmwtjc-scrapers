"""
Use Playwright headless Chrome to solve Cloudflare's JS challenge and extract
the cf_clearance cookie. Saves cookies to cf_cookies.json in cwd.

Exit 0 = success, Exit 1 = failed to get cookie.
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

TARGET_URL  = "https://www.plumbnation.co.uk/"
OUTPUT_FILE = "cf_cookies.json"
USER_AGENT  = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def get_cf_cookies():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # Skip images/fonts — we only need the cookies
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot,ico}",
            lambda r: r.abort(),
        )

        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
            # CF JS challenge changes the title from "Just a moment..." when done
            page.wait_for_function(
                "() => document.title !== \'Just a moment...\'",
                timeout=30_000,
            )
            print(f"[cf_cookie] Page title: {page.title()}", file=sys.stderr)
        except PlaywrightTimeout:
            print("[cf_cookie] Timed out waiting for CF challenge", file=sys.stderr)

        all_cookies = context.cookies()
        browser.close()

    cf = {c["name"]: c["value"] for c in all_cookies
          if c["name"] in ("cf_clearance", "__cf_bm", "__cflb")}
    return cf


if __name__ == "__main__":
    print("[cf_cookie] Launching headless Chrome to solve CF challenge…", file=sys.stderr)
    cookies = get_cf_cookies()

    if not cookies.get("cf_clearance"):
        print("[cf_cookie] WARNING: cf_clearance not obtained — scrape may fail", file=sys.stderr)
        sys.exit(1)

    print(f"[cf_cookie] Got cookies: {list(cookies)}", file=sys.stderr)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"[cf_cookie] Saved to {OUTPUT_FILE}", file=sys.stderr)
    sys.exit(0)
