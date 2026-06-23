import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderSelco(scrapy.Spider):
    """
    Selco product data is embedded in the Apollo GraphQL cache on each category
    page as a raw JSON script tag. Each category page holds up to 15 products
    (FredhopperItem entries). Pages with more than 15 products have additional
    pages at ?page=N. The spider fetches page 1 and follows pagination.

    Run against url.csv produced by sitemap_spider_selco (leaf category URLs).
    """
    name = "product_spider_selco"
    supplier_name = "Selco"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={"impersonate": "chrome120", "page": 1},
                )

    def _parse_apollo_cache(self, html):
        """Return the parsed Apollo cache dict from the raw JSON script tag."""
        script_tags = re.findall(
            r"<script[^>]*>(.*?)</script>", html, re.DOTALL
        )
        for s in script_tags:
            s = s.strip()
            if s.startswith("{") and "ProductInfo:" in s:
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
        return {}

    def _extract_products(self, cache):
        """Yield dicts from FredhopperItem entries in the Apollo cache."""
        for k, v in cache.items():
            if isinstance(v, dict) and v.get("__typename") == "FredhopperItem":
                url_key = v.get("url_key", "")
                name = v.get("name") or v.get("product_name")
                sku = v.get("p_sku")
                image = v.get("_thumburl")
                # price is ex-VAT, price_incl_tax is inc-VAT
                price_ex = (v.get("price") or "").replace("£", "").strip()
                price_inc = (v.get("price_incl_tax") or "").replace("£", "").strip()
                if not name or not url_key:
                    continue
                yield {
                    "url_key": url_key,
                    "name": name,
                    "sku": sku,
                    "image": image,
                    "price_ex": price_ex or None,
                    "price_inc": price_inc or None,
                }

    def _get_pagination(self, cache):
        """Return (current_page, number_of_pages) from FredhopperPagination."""
        for v in cache.values():
            if isinstance(v, dict) and v.get("__typename") == "FredhopperPagination":
                return v.get("current_page", 1), v.get("number_of_pages", 1)
        return 1, 1

    def parse(self, response):
        html = response.text
        cache = self._parse_apollo_cache(html)
        if not cache:
            return

        now = datetime.utcnow().isoformat()
        base_url = response.url.split("?")[0]

        for prod in self._extract_products(cache):
            product_url = f"https://www.selcobw.com/{prod['url_key']}"
            yield {
                "supplier": self.supplier_name,
                "source_url": product_url,
                "scraped_at": now,
                "product": {
                    "name": prod["name"],
                    "description": None,
                    "brand": None,
                    "sku": prod["sku"],
                    "mpn": None,
                    "gtin13": None,
                    "category": base_url.replace("https://www.selcobw.com/products/", ""),
                    "image_urls": [prod["image"]] if prod["image"] else [],
                    "offer_url": product_url,
                    # Use ex-VAT price to match other trade supplier conventions
                    "price": prod["price_ex"],
                    "currency": "GBP",
                    "availability": None,
                    "in_stock": None,
                    "stock_count": None,
                    "delivery_info": "Click & Collect available at branches; delivery available",
                },
            }

        current_page, total_pages = self._get_pagination(cache)
        if current_page < total_pages:
            next_page = current_page + 1
            yield scrapy.Request(
                url=f"{base_url}?page={next_page}",
                callback=self.parse,
                meta={"impersonate": "chrome120", "page": next_page},
            )
