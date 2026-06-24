#!/usr/bin/env python3
"""
Fetch all Grant & Stone products via their Magento 2 GraphQL API.
Usage: python fetch_products_grantandstone.py <output_path.json>
"""
import json
import sys
import time
from datetime import datetime, timezone

from curl_cffi import requests

BASE_URL = "https://www.grantandstone.co.uk"
GRAPHQL = f"{BASE_URL}/graphql"
PAGE_SIZE = 100
SUPPLIER = "Grant & Stone"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
}

QUERY = """
query GetProducts($page: Int!) {
    products(search: "", pageSize: 100, currentPage: $page, sort: {name: ASC}) {
        total_count
        page_info { total_pages }
        items {
            name
            sku
            url_key
            description { html }
            image { url }
            price_range {
                minimum_price {
                    final_price { value currency }
                }
            }
            stock_status
            categories { name url_key }
        }
    }
}
"""


def fetch_page(page: int) -> dict:
    for attempt in range(3):
        try:
            resp = requests.post(
                GRAPHQL,
                json={"query": QUERY, "variables": {"page": page}},
                headers=HEADERS,
                timeout=30,
                impersonate="chrome120",
            )
            resp.raise_for_status()
            return resp.json()["data"]["products"]
        except Exception as e:
            if attempt == 2:
                raise
            print(f"[GrantAndStone] Page {page} attempt {attempt+1} failed: {e} — retrying")
            time.sleep(2)


def main():
    output_path = sys.argv[1]
    scraped_at = datetime.now(timezone.utc).isoformat()

    results = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        data = fetch_page(page)
        total_pages = data["page_info"]["total_pages"]
        print(
            f"[GrantAndStone] Page {page}/{total_pages} "
            f"— {data['total_count']} total products",
            flush=True,
        )

        for item in data["items"]:
            price_obj = item["price_range"]["minimum_price"]["final_price"]
            price = price_obj["value"]
            currency = price_obj.get("currency", "GBP")

            cats = item.get("categories") or []
            category = cats[0]["name"] if cats else ""
            breadcrumb = [c["name"] for c in cats]

            image = (item.get("image") or {}).get("url") or ""

            results.append({
                "supplier": SUPPLIER,
                "source_url": f"{BASE_URL}/{item['url_key']}",
                "scraped_at": scraped_at,
                "name": item["name"],
                "description": (item.get("description") or {}).get("html") or "",
                "brand": None,
                "sku": item["sku"],
                "image_urls": [image] if image else [],
                "price": round(price, 2) if price is not None else None,
                "currency": currency,
                "availability": (
                    "InStock" if item["stock_status"] == "IN_STOCK" else "OutOfStock"
                ),
                "stock_count": "",
                "category": category,
                "breadcrumb": breadcrumb,
                "breadcrumb_str": " > ".join(breadcrumb) if breadcrumb else None,
            })

        page += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f)

    print(f"[GrantAndStone] Done — {len(results)} products written to {output_path}")


if __name__ == "__main__":
    main()
