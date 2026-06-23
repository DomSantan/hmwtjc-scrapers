import csv
import json
import re
from datetime import datetime

import scrapy


class ProductSpiderBes(scrapy.Spider):
    name = "product_spider_bes"
    supplier_name = "BES"

    # Delivery: free over £50 ex-VAT, otherwise £4.95 + VAT, next-day by 9pm
    DELIVERY_INFO = "Free delivery over £50 ex VAT; £4.95 otherwise. Next day by 9pm Mon–Fri."

    def start_requests(self):
        with open("url.csv", newline="") as f:
            for row in csv.DictReader(f):
                url = row.get("url", "").strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        if response.status != 200:
            self.logger.warning(f"Non-200 {response.status}: {response.url}")
            return

        scraped_at = datetime.utcnow().isoformat()

        # ── Extract Product ld+json ──────────────────────────────────────────
        product_data = None
        for block in response.xpath('//script[@type="application/ld+json"]/text()').getall():
            try:
                data = json.loads(block.strip())
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            product_data = item
                            break
                elif isinstance(data, dict) and data.get("@type") == "Product":
                    product_data = data
            except (json.JSONDecodeError, ValueError):
                continue
            if product_data:
                break

        if not product_data:
            self.logger.debug(f"No Product ld+json at {response.url}")
            return

        offer = product_data.get("offers", {})
        if isinstance(offer, list):
            offer = offer[0] if offer else {}

        name = product_data.get("name", "").strip()
        sku = product_data.get("sku")
        brand_raw = product_data.get("brand", {})
        brand = (
            brand_raw.get("name") if isinstance(brand_raw, dict) else str(brand_raw)
        ) or "Unbranded"
        if brand.lower() in ("unbranded", ""):
            brand = "BES"

        image = product_data.get("image", "")
        if isinstance(image, list):
            image = image[0] if image else ""

        avail_raw = offer.get("availability", "").split("/")[-1]

        try:
            base_price = float(offer.get("price", 0))
        except (TypeError, ValueError):
            base_price = None

        if not name or not base_price:
            return

        base_item = {
            "supplier": self.supplier_name,
            "name": name,
            "sku": sku,
            "brand": brand,
            "price": base_price,
            "unit": "each",
            "image_urls": [image] if image else [],
            "offer_url": response.url,
            "source_url": response.url,
            "availability": avail_raw,
            "delivery_info": self.DELIVERY_INFO,
            "scraped_at": scraped_at,
        }
        yield base_item

        # ── Bulk pricing tiers ───────────────────────────────────────────────
        # Table rows: each <tr> in #product_bulk_discount holds qty | price | saving
        for row in response.css("#product_bulk_discount table tr"):
            qty_text = row.css("td.item:first-child::text").get("").strip()
            # qty looks like "50+" — extract the number
            qty_match = re.match(r"(\d+)", qty_text)
            if not qty_match:
                continue

            qty_min = int(qty_match.group(1))

            # Ex-VAT price lives in price-excluding-tax span's data-price-amount attribute
            ex_vat_amount = row.css(
                "span.price-wrapper.price-excluding-tax::attr(data-price-amount)"
            ).get()
            if not ex_vat_amount:
                continue

            try:
                tier_price = float(ex_vat_amount)
            except (TypeError, ValueError):
                continue

            if tier_price <= 0 or tier_price >= base_price:
                continue

            yield {
                **base_item,
                "price": tier_price,
                "unit": f"each ({qty_min}+)",
            }
