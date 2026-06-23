"""
Screwfix product spider.

Reads search-results URLs from url.csv (one per heating/bathroom category,
produced by sitemap_spider_screwfix).  Each search page embeds an
ItemList JSON-LD in the SSR HTML containing up to 20 products with names,
SKUs, prices and images.

If the page also contains a "next page" link, the spider follows it so
that categories with more than 20 products get fuller coverage.

Output: products.json
"""
import csv
import json
import re
import extruct
from urllib.parse import urljoin
from w3lib.html import get_base_url
from datetime import datetime
import scrapy

BASE_URL = "https://www.screwfix.com"

# Screwfix delivery note (standard public rates June 2026)
DELIVERY_POLICY = "Free delivery over £75 (or free with ProPlus over £35); standard £5"


class ProductSpiderScrewfix(scrapy.Spider):
    name = "product_spider_screwfix"
    supplier_name = "Screwfix"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        if response.status != 200:
            return

        base_url = get_base_url(response.text, response.url)
        try:
            metadata = extruct.extract(
                        response.text,
                        base_url=base_url,
                        syntaxes=["json-ld"],
                        uniform=True,
                    )
        except Exception as e:
            self.logger.warning(f"extruct failed on {response.url}: {e}")
            return

        items_yielded = 0
        for ld in metadata.get("json-ld", []):
            if ld.get("@type") != "ItemList":
                continue

            for item in ld.get("itemListElement", []):
                if item.get("@type") != "Product":
                    continue

                offer = item.get("offers", {})
                if isinstance(offer, list):
                    offer = offer[0] if offer else {}

                price_raw = offer.get("price")
                try:
                    price = float(price_raw) if price_raw not in (None, "", "null") else None
                except (ValueError, TypeError):
                    price = None

                # URL in ItemList is relative (/p/product-name/12345)
                product_url_raw = item.get("url", "")
                product_url = urljoin(BASE_URL, product_url_raw) if product_url_raw else ""

                image = item.get("image", "")
                image_urls = [image] if isinstance(image, str) and image else (
                    image if isinstance(image, list) else []
                )

                yield {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "name": item.get("name"),
                    "sku": item.get("sku"),
                    "brand": None,
                    "description": item.get("description", "").strip(),
                    "image_urls": image_urls,
                    "availability": "",
                    "stock_count": "",
                    "price": price,
                    "currency": offer.get("priceCurrency", "GBP"),
                    "offer_url": product_url,
                    "delivery_policy": DELIVERY_POLICY,
                }
                items_yielded += 1

        # Follow the next-page link if there is one and we found products
        if items_yielded > 0:
            next_url = self._next_page_url(response)
            if next_url:
                yield scrapy.Request(
                    url=next_url,
                    callback=self.parse,
                    meta={"impersonate": "chrome120"},
                )

    def _next_page_url(self, response):
        """Return the next-page URL if the page has a visible pagination link."""
        # Screwfix next page: <a rel="next" href="..."> or data-qaid="next-page"
        href = response.xpath(
            '//a[@rel="next"]/@href | //a[@data-qaid="next-page-link"]/@href'
        ).get()
        if href:
            return urljoin(BASE_URL, href)

        # Fallback: look for ?start= pattern and increment by 20
        current = response.url
        start_match = re.search(r"[?&]start=(\d+)", current)
        current_start = int(start_match.group(1)) if start_match else 0

        # Only follow if the page had a full 20 results (avoid endless empty pages)
        total_re = re.search(r"numberOfItems.*?(\d+)", response.text)
        if total_re and int(total_re.group(1)) >= 20:
            sep = "&" if "?" in current else "?"
            next_start = current_start + 20
            return f"{current}{sep}start={next_start}"

        return None
