"""
PlumbNation product fetcher using curl_cffi sessions directly.

Key difference from scrapy-impersonate:
- Persistent HTTPS session per thread (HTTP/2 connection reuse)
- Full Chrome headers (Sec-Fetch-*, Sec-Ch-Ua, etc.)
- Cookie jar maintained across all requests in the session
- Low concurrency so CF sees browser-like request patterns
"""
import csv
import json
import os
import sys
import threading
from datetime import datetime, timezone
from queue import Empty, Queue

import extruct
from curl_cffi import requests as cffi_requests
from w3lib.html import get_base_url

COOKIES_FILE = "cf_cookies.json"
URL_CSV      = "url.csv"
CONCURRENCY  = 5

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _load_cookies():
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE) as f:
            return json.load(f)
    return {}


def _extract(url, html):
    try:
        meta = extruct.extract(html, base_url=get_base_url(html, url),
                               syntaxes=["json-ld"], uniform=True)
    except Exception:
        return None
    product = next(
        (i for i in meta.get("json-ld", []) if i.get("@type") == "Product"), None
    )
    if not product:
        return None
    offers_raw = product.get("offers", {})
    if isinstance(offers_raw, dict):
        offers = [offers_raw]
    elif isinstance(offers_raw, list):
        offers = offers_raw
    else:
        offers = []
    offer = offers[0] if offers else {}
    images = product.get("image", [])
    if isinstance(images, str):
        images = [images]
    brand_raw = product.get("brand", {})
    brand = brand_raw.get("name") if isinstance(brand_raw, dict) else brand_raw
    return {
        "supplier": "PlumbNation",
        "source_url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "product": {
            "name":         product.get("name"),
            "description":  product.get("description", "").strip(),
            "brand":        brand,
            "mpn":          product.get("mpn"),
            "sku":          product.get("sku"),
            "image_urls":   images,
            "price":        offer.get("price") or offer.get("lowPrice"),
            "currency":     offer.get("priceCurrency", "GBP"),
            "availability": "InStock" if "InStock" in offer.get("availability", "") else "OutOfStock",
        },
    }


def worker(q, results, lock, cookies, done_counter, sample_log):
    session = cffi_requests.Session(impersonate="chrome124")
    session.cookies.update(cookies)
    while True:
        try:
            url = q.get(timeout=5)
        except Empty:
            break
        try:
            resp = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            with lock:
                if sample_log[0] < 5:
                    snippet = resp.text[:200].replace("\n", " ").strip()
                    print(f"[plumbnation] sample status={resp.status_code} url={url}", file=sys.stderr)
                    print(f"[plumbnation] sample html={snippet!r}", file=sys.stderr)
                    sample_log[0] += 1
            if resp.status_code == 200:
                item = _extract(url, resp.text)
                if item:
                    with lock:
                        results.append(item)
        except Exception as exc:
            with lock:
                if sample_log[0] < 5:
                    print(f"[plumbnation] exception: {type(exc).__name__}: {exc}", file=sys.stderr)
                    sample_log[0] += 1
        finally:
            q.task_done()
            with lock:
                done_counter[0] += 1
                if done_counter[0] % 500 == 0:
                    print(f"[plumbnation] {done_counter[0]} done, {len(results)} items", file=sys.stderr)


def main(output_file):
    cookies = _load_cookies()
    print(f"[plumbnation] {len(cookies)} cookies loaded", file=sys.stderr)
    urls = []
    with open(URL_CSV) as f:
        for row in csv.DictReader(f):
            u = row["url"].strip()
            if u:
                urls.append(u)
    print(f"[plumbnation] {len(urls)} URLs, {CONCURRENCY} threads", file=sys.stderr)
    q = Queue()
    for u in urls:
        q.put(u)
    results, lock, done_counter, sample_log = [], threading.Lock(), [0], [0]
    threads = [
        threading.Thread(target=worker, args=(q, results, lock, cookies, done_counter, sample_log), daemon=True)
        for _ in range(CONCURRENCY)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"[plumbnation] Done — {len(results)} items", file=sys.stderr)
    with open(output_file, "w") as f:
        json.dump(results, f)
    return len(results)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("output", nargs="?", default="../../data/plumbnation.json")
    args = p.parse_args()
    sys.exit(0 if main(args.output) > 0 else 1)
