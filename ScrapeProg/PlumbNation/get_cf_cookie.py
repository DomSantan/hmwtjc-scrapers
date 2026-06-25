"""
SeleniumBase UC mode CF bypass for PlumbNation.

1. Hits the homepage first to establish a real CF session and get cookies.
2. Navigates to the sitemap index, finds the products sub-sitemap.
3. Extracts all product URLs and writes url.csv.
4. Saves all session cookies for the product spider.

Exit 0 = url.csv written, Exit 1 = failed.
"""
import csv
import json
import re
import sys
import time

OUTPUT_COOKIES = "cf_cookies.json"
OUTPUT_URLS    = "url.csv"
HOME_URL       = "https://www.plumbnation.co.uk/"
SITEMAP_URL    = "https://www.plumbnation.co.uk/sitemap.xml"


def _locs(source):
    return re.findall(r"<loc>\s*(https?://[^<]+?)\s*</loc>", source, re.IGNORECASE)


def run():
    from seleniumbase import SB

    with SB(uc=True, headless2=True, test=False) as sb:
        # Step 1: hit homepage to establish a real CF session + get cookies
        print("[cf_cookie] Loading homepage to establish CF session…", file=sys.stderr)
        sb.uc_open_with_reconnect(HOME_URL, reconnect_time=6)
        for _ in range(20):
            if "just a moment" not in sb.get_title().lower():
                break
            time.sleep(1)
        print(f"[cf_cookie] Homepage title: {sb.get_title()}", file=sys.stderr)

        # Grab cookies now — these are the session cookies for product pages
        all_cookies = {c["name"]: c["value"] for c in sb.get_cookies()}
        print(f"[cf_cookie] Got {len(all_cookies)} cookies after homepage: {list(all_cookies)}", file=sys.stderr)

        # Step 2: navigate to sitemap index
        print("[cf_cookie] Loading sitemap index…", file=sys.stderr)
        sb.open(SITEMAP_URL)
        time.sleep(3)
        source = sb.get_page_source()

        locs = _locs(source)
        sub_sitemaps = [l for l in locs if l.rstrip("/").endswith((".xml", ".xml.gz"))]
        print(f"[cf_cookie] Found {len(sub_sitemaps)} sub-sitemaps: {sub_sitemaps}", file=sys.stderr)

        # Step 3: pick the products sub-sitemap
        product_sitemaps = [l for l in sub_sitemaps if "product" in l.lower()]
        if not product_sitemaps:
            # Fall back to all sub-sitemaps if none tagged as products
            print("[cf_cookie] No product sub-sitemap found — using all", file=sys.stderr)
            product_sitemaps = sub_sitemaps

        page_urls = []
        for sub_url in product_sitemaps:
            print(f"[cf_cookie] Loading {sub_url}…", file=sys.stderr)
            sb.open(sub_url)
            time.sleep(2)
            sub_locs = _locs(sb.get_page_source())
            page_locs = [l for l in sub_locs if not l.rstrip("/").endswith((".xml", ".xml.gz"))]
            print(f"[cf_cookie]   → {len(page_locs)} URLs", file=sys.stderr)
            page_urls.extend(page_locs)

        # Refresh cookies after all navigation — session may have been updated
        all_cookies = {c["name"]: c["value"] for c in sb.get_cookies()}
        print(f"[cf_cookie] Final cookies ({len(all_cookies)}): {list(all_cookies)}", file=sys.stderr)

        return all_cookies, page_urls


if __name__ == "__main__":
    print("[cf_cookie] Launching SeleniumBase UC Chrome…", file=sys.stderr)
    try:
        cookies, urls = run()
    except Exception as e:
        print(f"[cf_cookie] Error: {e}", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_COOKIES, "w") as f:
        json.dump(cookies, f)
    print(f"[cf_cookie] Saved {len(cookies)} cookies to {OUTPUT_COOKIES}", file=sys.stderr)

    if not urls:
        print("[cf_cookie] No product URLs found — aborting", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_URLS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in urls:
            w.writerow([u])
    print(f"[cf_cookie] Wrote {len(urls)} product URLs to {OUTPUT_URLS}", file=sys.stderr)
    sys.exit(0)
