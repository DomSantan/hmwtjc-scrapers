import scrapy
import csv
import json
import re
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_toolstation"
    supplier_name = "Toolstation"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url and '/p' in url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def _extract_delivery(self, response):
        """Parse delivery info from page text."""
        # Decode HTML entities and strip tags
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'&#\d+;', lambda m: chr(int(m.group(0)[2:-1])), text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'\s+', ' ', text)

        delivery = {
            "delivery_free_threshold_gbp": None,
            "delivery_standard_charge_gbp": None,
            "delivery_cutoff": None,
        }

        # Free delivery threshold — "FREE for orders over £40" or "FREE DELIVERY On orders over £40"
        free_m = re.search(r'(?:free delivery|FREE)\s+(?:on )?orders? over\s*[£$]?([\d.]+)', text, re.IGNORECASE)
        if free_m:
            delivery["delivery_free_threshold_gbp"] = float(free_m.group(1))

        # Standard charge — "£5.00" or "£5" near "delivery"
        charge_m = re.search(r'Next Day Delivery[^£]*[£$]([\d.]+)', text, re.IGNORECASE)
        if charge_m:
            delivery["delivery_standard_charge_gbp"] = float(charge_m.group(1))

        # Order cutoff — "Order before 9pm Monday to Thursday"
        cutoff_m = re.search(r'Order before\s+(.{5,50}?)\s+for next', text, re.IGNORECASE)
        if cutoff_m:
            delivery["delivery_cutoff"] = cutoff_m.group(1).strip()

        return delivery

    def _parse_product(self, data, source_url, scraped_at, delivery, breadcrumb_list):
        image = data.get("image", "")
        images = [image] if isinstance(image, str) and image else (image if isinstance(image, list) else [])

        offer = data.get("offers", {})
        if isinstance(offer, list):
            offer = offer[0] if offer else {}

        avail = offer.get("availability", "").split("/")[-1]

        return {
            "supplier": self.supplier_name,
            "source_url": source_url,
            "scraped_at": scraped_at,
            "name": data.get("name"),
            "description": data.get("description", "").strip(),
            "brand": data.get("brand"),
            "sku": data.get("sku"),
            "image_urls": images,
            "offer_url": data.get("url") or data.get("@id") or source_url,
            "price": offer.get("price"),
            "currency": offer.get("priceCurrency", "GBP"),
            "availability": avail,
            "stock_count": "",
            "rating_value": data.get("aggregateRating", {}).get("ratingValue"),
            "review_count": data.get("aggregateRating", {}).get("reviewCount"),
            "breadcrumb": breadcrumb_list,
            "breadcrumb_str": " > ".join(breadcrumb_list) if breadcrumb_list else None,
            **delivery,
        }

    def parse(self, response):
        ld_json_scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        breadcrumb_list = []
        scraped_at = datetime.utcnow().isoformat()
        delivery = self._extract_delivery(response)

        for ld_json in ld_json_scripts:
            try:
                data = json.loads(ld_json)
            except json.JSONDecodeError:
                continue

            if data.get("@type") == "BreadcrumbList":
                breadcrumb_list = [
                    item.get("item", {}).get("name")
                    for item in data.get("itemListElement", [])
                    if isinstance(item.get("item", {}), dict)
                ]

            if data.get("@type") == "Product":
                # Base product
                yield self._parse_product(data, response.url, scraped_at, delivery, breadcrumb_list)

                # Variants via hasVariant
                for variant in data.get("hasVariant", []):
                    if not isinstance(variant, dict):
                        continue
                    yield self._parse_product(variant, response.url, scraped_at, delivery, breadcrumb_list)
