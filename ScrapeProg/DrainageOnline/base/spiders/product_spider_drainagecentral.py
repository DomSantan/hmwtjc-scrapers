import re
import scrapy
import csv
import extruct
from w3lib.html import get_base_url
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_drainageonline"
    supplier_name = "Drainage Online"

    def start_requests(self):
        with open("urls.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def _extract_delivery_days(self, description):
        """Pull 'X-Y working days' out of description text if present."""
        m = re.search(r'(\d+[-–]\d+|\d+)\s*working days?', description, re.IGNORECASE)
        return m.group(0).strip() if m else ""

    def parse(self, response):
        base_url = get_base_url(response.text, response.url)
        metadata = extruct.extract(
            response.text,
            base_url=base_url,
            syntaxes=["json-ld"],
            uniform=True
        )

        jsonld = metadata.get("json-ld", [])

        # Main product image from HTML (not in JSON-LD)
        image_url = response.xpath('//img[@id="product-main-image"]/@src').get("")
        if image_url and image_url.startswith("/"):
            image_url = "https://www.drainageonline.co.uk" + image_url

        for entry in jsonld:
            if entry.get("@type") != "ItemList":
                continue

            for element in entry.get("itemListElement", []):
                product = element.get("item", {})
                offer = product.get("offers", {})
                description = product.get("description", "").strip()

                yield {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": datetime.utcnow().isoformat(),

                    "product": {
                        "position": element.get("position"),
                        "name": product.get("name"),
                        "description": description,
                        "brand": product.get("brand", {}).get("name")
                                 if isinstance(product.get("brand"), dict)
                                 else product.get("brand"),
                        "color": product.get("color"),
                        "sku": product.get("sku"),
                        "gtin13": product.get("gtin13"),
                        "image_urls": [image_url] if image_url else [],
                        "price": offer.get("price"),
                        "currency": offer.get("priceCurrency"),
                        "availability": offer.get("availability", "").split("/")[-1],
                        "offer_url": offer.get("url"),
                        "seller": offer.get("seller", {}).get("name")
                                  if isinstance(offer.get("seller"), dict)
                                  else offer.get("seller"),
                        "delivery_days": self._extract_delivery_days(description),
                    }
                }
