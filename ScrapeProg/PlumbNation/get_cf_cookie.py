"""
SeleniumBase UC mode: disconnects Chrome DevTools Protocol during the CF
challenge so Cloudflare can't detect automation signals.

Exit 0 = cf_clearance obtained, Exit 1 = failed.
"""
import json
import sys
import time

OUTPUT_FILE = "cf_cookies.json"
TARGET_URL = "https://www.plumbnation.co.uk/"


def get_cf_cookies():
    from seleniumbase import SB

    # headless2 uses Chrome's newer --headless=new flag, less detectable than
    # classic headless. uc=True patches out the automation indicators.
    with SB(uc=True, headless2=True, test=False) as sb:
        # uc_open_with_reconnect: opens page, drops the CDP connection so CF
        # can't fingerprint it during the challenge, waits reconnect_time
        # seconds, then reconnects once the challenge should be solved.
        sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)

        # Poll until "Just a moment..." title is gone (up to 30s)
        for _ in range(30):
            title = sb.get_title()
            if "just a moment" not in title.lower():
                break
            time.sleep(1)

        title = sb.get_title()
        print(f"[cf_cookie] Page title: {title}", file=sys.stderr)

        raw = sb.get_cookies()
        return {c["name"]: c["value"] for c in raw
                if c["name"] in ("cf_clearance", "__cf_bm", "__cflb")}


if __name__ == "__main__":
    print("[cf_cookie] Launching SeleniumBase UC Chrome…", file=sys.stderr)
    try:
        cookies = get_cf_cookies()
    except Exception as e:
        print(f"[cf_cookie] Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not cookies.get("cf_clearance"):
        print("[cf_cookie] WARNING: cf_clearance not obtained", file=sys.stderr)
        sys.exit(1)

    print(f"[cf_cookie] Got cookies: {list(cookies)}", file=sys.stderr)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"[cf_cookie] Saved to {OUTPUT_FILE}", file=sys.stderr)
    sys.exit(0)
