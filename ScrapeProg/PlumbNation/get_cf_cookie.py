"""
SeleniumBase UC mode CF bypass for PlumbNation.

Navigates directly to the sitemap URL, saves ALL browser cookies for the
product spider, and parses sitemap URLs into url.csv so the Scrapy sitemap
spider can be skipped entirely.

Exit 0 = url.csv written (URLs found), Exit 1 = failed.
"""
import csv
import json
import re
import sys
import time

OUTPUT_COOKIES = "cf_cookies.json"
OUTPUT_URLS    = "url.csv"
SITEMAP_URL    = "https://www.plumbnation.co.uk/sitemap.xml"


def _locs(source):
    return re.findall(r"<loc>\s*(https?://[^<]+?)\s*</loc>", source, re.IGNORECASE)


def run():
    from seleniumbase import SB

    with SB(uc=True, headless2=True, test=False) as sb:
        # Navigate to the sitemap directly — UC disconnects CDP during load
        # so CF cannot detect automation during the challenge window.
        sb.uc_open_with_reconnect(SITEMAP_URL, reconnect_time=6)

        for _ in range(20):
            if "just a moment" not in sb.get_title().lower():
                break
            time.sleep(1)

        print(f"[cf_cookie] Sitemap title: {sb.get_title()}", file=sys.stderr)
        source = sb.get_page_source()

        # Persist ALL cookies — CF may rely on session cookies beyond cf_clearance
        all_cookies = {c["name"]: c["value"] for c in sb.get_cookies()}
        with open(OUTPUT_COOKIES, "w") as f:
            json.dump(all_cookies, f)
        print(f"[cf_cookie] Saved {len(all_cookies)} cookies: {list(all_cookies)}", file=sys.stderr)

        # Parse sitemap (handle both sitemap index and plain sitemap)
        locs = _locs(source)
        sub_sitemaps = [l for l in locs if l.rstrip("/").endswith((".xml", ".xml.gz"))]
        page_urls    = [l for l in locs if l not in sub_sitemaps]

        if sub_sitemaps and not page_urls:
            print(f"[cf_cookie] Sitemap index: {len(sub_sitemaps)} sub-sitemaps", file=sys.stderr)
            for sub_url in sub_sitemaps:
                sb.open(sub_url)
                time.sleep(2)
                sub_locs = _locs(sb.get_page_source())
                page_urls.extend(l for l in sub_locs if not l.rstrip("/").endswith((".xml", ".xml.gz")))

        print(f"[cf_cookie] Found {len(page_urls)} URLs", file=sys.stderr)
        return page_urls


if __name__ == "__main__":
    print("[cf_cookie] Launching SeleniumBase UC Chrome…", file=sys.stderr)
    try:
        urls = run()
    except Exception as e:
        print(f"[cf_cookie] Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not urls:
        print("[cf_cookie] No URLs extracted — sitemap may still be blocked", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_URLS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in urls:
            w.writerow([u])
    print(f"[cf_cookie] Wrote {len(urls)} URLs to {OUTPUT_URLS}", file=sys.stderr)
    sys.exit(0)
