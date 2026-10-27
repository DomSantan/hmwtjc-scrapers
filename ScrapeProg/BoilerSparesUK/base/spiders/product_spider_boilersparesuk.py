import csv
import json
import re
import scrapy
from datetime import datetime


class ProductSpider(scrapy.Spider):
    name = "product_spider_boilersparesuk"
    supplier_name = "Boiler Spares UK"

    def start_requests(self):
        with open("urls.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                if url:
                    yield scrapy.Request(url=url, callback=self.parse)

    def _json_ld_product(self, response):
        for raw in response.xpath('//script[@type="application/ld+json"]/text()').getall():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return None

    def parse(self, response):
        # Site rebuilt Oct 2026 (/part/ pages). JSON-LD carries name/sku/brand/stock,
        # but its price is INC VAT. The importer treats Boiler Spares UK as ex-VAT, so
        # take the "£x ex VAT" figure shown next to it and check the two agree.
        data = self._json_ld_product(response)
        if not data or not data.get("name"):
            return

        offer = data.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        price_inc = offer.get("price")
        if price_inc in (None, ""):
            return  # "Call for price" parts have no offer price

        price_ex = None
        m = re.search(r"£\s*([\d,]+\.\d{2})\s*ex\s*VAT", response.text, re.I)
        if m:
            price_ex = float(m.group(1).replace(",", ""))
            if abs(price_ex * 1.2 - float(price_inc)) > 0.02:
                self.logger.warning(f"VAT mismatch on {response.url}: ex {price_ex} vs inc {price_inc}")
                return
        else:
            price_ex = round(float(price_inc) / 1.2, 2)

        brand = data.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        availability = offer.get("availability", "")

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "product": {
                "name": data["name"].strip(),
                "brand": brand or "",
                "sku": data.get("sku"),
                "mpn": data.get("mpn"),
                "price": f"{price_ex:.2f}",
                "currency": offer.get("priceCurrency", "GBP"),
                "availability": availability,
                "in_stock": availability.lower().endswith("instock") if availability else None,
            },
        }
