import csv
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

    def parse(self, response):
        name = response.css("[itemprop=name]::text").get("").strip()
        description = response.css("[itemprop=description]::text").get("").strip()
        price_raw = response.css("[itemprop=price]::text").get("").strip()
        price = re.sub(r"[^\d.]", "", price_raw) or None

        if not name:
            return

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "product": {
                "name": name,
                "description": description,
                "price": price,
                "currency": "GBP",
            },
        }
