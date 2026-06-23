import scrapy
import csv
import json
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_wickes"
    supplier_name = "Wickes"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url and '/p/' in url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        ld_json_scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()

        product_data = {}
        breadcrumb_list = []

        for ld_json in ld_json_scripts:
            try:
                data = json.loads(ld_json)
            except json.JSONDecodeError:
                continue

            if data.get("@type") == "BreadcrumbList":
                breadcrumb_list = [
                    item["item"]["name"]
                    for item in data.get("itemListElement", [])
                    if "item" in item and "name" in item["item"]
                ]

            if data.get("@type") == "Product":
                images = data.get("image", [])
                if isinstance(images, str):
                    images = [images]
                elif not isinstance(images, list):
                    images = []

                offer = data.get("offers", {})
                if isinstance(offer, list):
                    offer = offer[0] if offer else {}

                brand = data.get("brand")
                brand_name = brand.get("name") if isinstance(brand, dict) else brand

                avail = offer.get("availability", "")
                avail_clean = avail.split("/")[-1] if avail else ""

                product_data = {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "name": data.get("name"),
                    "description": data.get("description", "").strip(),
                    "brand": brand_name,
                    "mpn": data.get("mpn"),
                    "gtin13": data.get("gtin13"),
                    "sku": data.get("sku"),
                    "image_urls": images,
                    "offer_url": data.get("url") or offer.get("url"),
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": avail_clean,
                    "stock_count": "",
                    "rating_value": data.get("aggregateRating", {}).get("ratingValue"),
                    "review_count": data.get("aggregateRating", {}).get("reviewcount"),
                }

        if product_data:
            yield {
                **product_data,
                "breadcrumb": breadcrumb_list,
                "breadcrumb_str": " > ".join(breadcrumb_list) if breadcrumb_list else None,
            }
