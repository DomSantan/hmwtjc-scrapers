import scrapy
import csv
import json
from datetime import datetime
from urllib.parse import urljoin


# Site-wide delivery policy (no product-specific delivery data in static HTML)
DELIVERY_POLICY = "Free delivery over £75 Ex VAT"


class ProductSpiderCityPlumbing(scrapy.Spider):
    name = "product_spider_cityplumbing"
    supplier_name = "City Plumbing"

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

    def parse(self, response):
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
            # Ensure absolute URLs (City Plumbing images start with //)
            images = [urljoin("https:", img) if img.startswith("//") else img for img in images]

            offer = data.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}

            brand = data.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")

            # City Plumbing JSON-LD doesn't include availability; no reliable
            # static signal, so leave as None
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
                    "offer_url": data.get("url") or response.url,
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": None,
                    "in_stock": None,
                    "stock_count": None,
                    "delivery_info": DELIVERY_POLICY,
                },
            }
