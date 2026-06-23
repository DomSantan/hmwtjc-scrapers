import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderVictorianPlumbing(scrapy.Spider):
    name = "product_spider_victorianplumbing"
    supplier_name = "Victorian Plumbing"

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
        Victorian Plumbing embeds a deliveryOptionLookup JSON blob per page.
        Uses raw_decode to parse the full object without regex boundary issues,
        then looks up the product's deliveryClass bucket.
        """
        try:
            cls_match = re.search(r'"deliveryClass":"([^"]+)"', html)
            lookup_start = html.find('"deliveryOptionLookup":')
            if not cls_match or lookup_start < 0:
                return None

            delivery_class = cls_match.group(1)
            brace_start = html.index('{', lookup_start)
            lookup, _ = json.JSONDecoder().raw_decode(html, brace_start)
            bucket = lookup.get(delivery_class, {})

            parts = []
            free = bucket.get("freeDelivery", {})
            if free:
                desc = (free.get("descriptor") or "").replace("¤", "£")
                parts.append(f"{free.get('method', 'Free delivery')}: {desc}")
            std = bucket.get("standardDelivery", {})
            if std:
                desc = (std.get("descriptor") or "").replace("¤", "£")
                parts.append(f"{std.get('method', 'Standard')}: {desc}")
            nwd = bucket.get("nextWorkingDay", {})
            if nwd:
                desc = (nwd.get("descriptor") or "").replace("¤", "£")
                parts.append(f"{nwd.get('method', 'Next Day')}: {desc}")
            return "; ".join(parts) if parts else None
        except Exception:
            return None

    def parse(self, response):
        html = response.text
        delivery_info = self._extract_delivery(html)

        ld_scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        for raw in ld_scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("@type") != "Product":
                continue

            images = data.get("image", [])
            images = images if isinstance(images, list) else [images]

            offer = data.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}

            brand = data.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")

            availability = offer.get("availability", "")
            in_stock = availability.lower().endswith("instock") if availability else None

            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),
                "product": {
                    "name": data.get("name"),
                    "description": (data.get("description") or "").strip(),
                    "brand": brand,
                    "sku": data.get("sku"),
                    "mpn": data.get("mpn"),
                    "category": data.get("category"),
                    "image_urls": images,
                    "offer_url": urljoin(response.url, offer.get("url", response.url)),
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": availability,
                    "in_stock": in_stock,
                    "stock_count": None,
                    "delivery_info": delivery_info,
                },
            }
