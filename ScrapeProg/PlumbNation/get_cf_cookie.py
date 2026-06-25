"""
SeleniumBase UC mode CF bypass for PlumbNation.

1. Hits the homepage to establish a CF session.
2. Fetches the products sitemap and writes url.csv.
3. Navigates to the first product URL in the same session so CF can
   issue a cf_clearance cookie (if it fires a challenge at all).
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
        # Step 1: homepage — establishes CF session
        print("[cf_cookie] Loading homepage…", file=sys.stderr)
        sb.uc_open_with_reconnect(HOME_URL, reconnect_time=6)
        for _ in range(20):
            if "just a moment" not in sb.get_title().lower():
                break
            time.sleep(1)
        print(f"[cf_cookie] Homepage title: {sb.get_title()}", file=sys.stderr)

        # Step 2: sitemap index
        sb.open(SITEMAP_URL)
        time.sleep(3)
        source = sb.get_page_source()
        locs = _locs(source)
        sub_sitemaps = [l for l in locs if l.rstrip("/").endswith((".xml", ".xml.gz"))]

        # Step 3: products sub-sitemap → url.csv
        product_sitemaps = [l for l in sub_sitemaps if "product" in l.lower()] or sub_sitemaps
        page_urls = []
        for sub_url in product_sitemaps:
            print(f"[cf_cookie] Loading {sub_url}…", file=sys.stderr)
            sb.open(sub_url)
            time.sleep(2)
            sub_locs = _locs(sb.get_page_source())
            page_locs = [l for l in sub_locs if not l.rstrip("/").endswith((".xml", ".xml.gz"))]
            print(f"[cf_cookie]   → {len(page_locs)} URLs", file=sys.stderr)
            page_urls.extend(page_locs)

        # Step 4: visit the first product page in the same session.
        # CF may issue cf_clearance here; the same cookie then covers all
        # product pages when passed to scrapy-impersonate.
        if page_urls:
            first_product = page_urls[0]
            print(f"[cf_cookie] Loading first product page to obtain cf_clearance: {first_product}", file=sys.stderr)
            sb.uc_open_with_reconnect(first_product, reconnect_time=6)
            for _ in range(25):
                if "just a moment" not in sb.get_title().lower():
                    break
                time.sleep(1)
            print(f"[cf_cookie] Product page title: {sb.get_title()}", file=sys.stderr)

        # Capture all cookies — including cf_clearance if CF issued one
        all_cookies = {c["name"]: c["value"] for c in sb.get_cookies()}
        cf_clearance = all_cookies.get("cf_clearance", "")
        print(f"[cf_cookie] Cookies ({len(all_cookies)}): {list(all_cookies)}", file=sys.stderr)
        if cf_clearance:
            print(f"[cf_cookie] cf_clearance obtained!", file=sys.stderr)
        else:
            print(f"[cf_cookie] No cf_clearance — scrapy will use session cookies only", file=sys.stderr)

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
    print(f"[cf_cookie] Saved {len(cookies)} cookies", file=sys.stderr)

    if not urls:
        print("[cf_cookie] No product URLs — aborting", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_URLS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in urls:
            w.writerow([u])
    print(f"[cf_cookie] Wrote {len(urls)} product URLs to {OUTPUT_URLS}", file=sys.stderr)
    sys.exit(0)
