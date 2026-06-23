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
                    meta={"impersonate": "chrome120"},
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
                    "gtin13": data.get("gtin13"),
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
