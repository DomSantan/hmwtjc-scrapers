import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderJewson(scrapy.Spider):
    name = "product_spider_jewson"
    supplier_name = "Jewson"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={"impersonate": "chrome120"},
                )

    def _extract_delivery(self, html):
        """
        Jewson product pages contain 'Free delivery*' and 'Next day delivery'
        in the page HTML. Click & Collect is also available site-wide.
        """
        parts = []
        if re.search(r'free\s+delivery', html, re.IGNORECASE):
            parts.append("Free delivery available")
        if re.search(r'next.?day\s+delivery', html, re.IGNORECASE):
            parts.append("Next day delivery available")
        if re.search(r'click\s*(?:&amp;|&|and)\s*collect', html, re.IGNORECASE):
            parts.append("Click & Collect available")
        return "; ".join(parts) if parts else None

    def parse(self, response):
        html = response.text
        blocks = re.findall(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            html, re.DOTALL
        )
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("@type") != "Product":
                continue

            offer = data.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}

            # Brand is a plain string on Jewson (not a dict)
            brand = data.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")

            images = data.get("image", [])
            if isinstance(images, str):
                images = [images]
            elif not isinstance(images, list):
                images = []

            gtin13 = data.get("gtin13") or None
            if gtin13 == "":
                gtin13 = None

            availability = offer.get("availability", "")
            in_stock = availability.lower().endswith("instock") if availability else None

            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),
                "product": {
                    "name": data.get("name"),
                    "description": re.sub(r'\s+', ' ', (data.get("description") or "")).strip(),
                    "brand": brand,
                    "sku": data.get("sku"),
                    "mpn": data.get("mpn"),
                    "gtin13": gtin13,
                    "category": data.get("category"),
                    "image_urls": images,
                    "offer_url": urljoin(response.url, offer.get("url", response.url)),
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": availability or None,
                    "in_stock": in_stock,
                    "stock_count": None,
                    "delivery_info": self._extract_delivery(html),
                },
            }
            return
