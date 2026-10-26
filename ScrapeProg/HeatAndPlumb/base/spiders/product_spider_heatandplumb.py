import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderHeatAndPlumb(scrapy.Spider):
    name = "product_spider_heatandplumb"
    supplier_name = "Heat and Plumb"

    # Heat and Plumb returns empty body without a proper Accept header
    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    }

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={"impersonate": "chrome133a"},
                )

    def _extract_delivery(self, response):
        """
        Extracts static delivery text from the product page.
        Next-day details are loaded via AJAX and not available in static HTML.
        """
        parts = []
        html = response.text
        if re.search(r'free\s+delivery\s+available', html, re.IGNORECASE):
            parts.append("Free Delivery Available")
        if re.search(r'next\s*[- ]?day\s+delivery', html, re.IGNORECASE):
            parts.append("Next Day Delivery available")
        if re.search(r'postcode\s+restrictions\s+apply', html, re.IGNORECASE):
            parts.append("postcode restrictions apply")
        return "; ".join(parts) if parts else None

    def parse(self, response):
        delivery_info = self._extract_delivery(response)

        ld_scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        for raw in ld_scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("@type") == "Product":
                item = self._build_item(data, response.url, response.url, delivery_info)
                if item:
                    yield item
            elif data.get("@type") == "ProductGroup":
                # Multi-variant parent pages (about half the sitemap) carry each variant's
                # price/SKU in hasVariant. These used to be skipped entirely, and a long run
                # of them tripped the circuit breaker at the same spot every night (~655 items).
                for variant in data.get("hasVariant") or []:
                    if not isinstance(variant, dict):
                        continue
                    merged = {**{k: data.get(k) for k in ("brand", "image", "description", "category")},
                              **{k: v for k, v in variant.items() if v}}
                    offer = merged.get("offers") or {}
                    if isinstance(offer, list):
                        offer = offer[0] if offer else {}
                    variant_url = urljoin(response.url, offer.get("url") or response.url)
                    item = self._build_item(merged, variant_url, response.url, delivery_info)
                    if item:
                        yield item

    def _build_item(self, data, source_url, page_url, delivery_info):
        # Variants are reachable both from their parent ProductGroup page and their own
        # ?variation= page; keep the first one seen this run.
        sku = data.get("sku")
        if sku:
            if not hasattr(self, "_seen_skus"):
                self._seen_skus = set()
            if sku in self._seen_skus:
                return None
            self._seen_skus.add(sku)

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

        return {
            "supplier": self.supplier_name,
            "source_url": source_url,
            "scraped_at": datetime.utcnow().isoformat(),
            "product": {
                "name": data.get("name"),
                "description": (data.get("description") or "").strip(),
                "brand": brand,
                "sku": sku,
                "mpn": data.get("mpn"),
                "gtin13": data.get("gtin13"),
                "category": data.get("category"),
                "image_urls": images,
                "offer_url": urljoin(page_url, offer.get("url", source_url)),
                "price": offer.get("price"),
                "currency": offer.get("priceCurrency", "GBP"),
                "availability": availability,
                "in_stock": in_stock,
                "stock_count": None,
                "delivery_info": delivery_info,
            },
        }
