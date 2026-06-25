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
        # Breadcrumb: Home » BRAND » BRAND MODEL NAME
        breadcrumb = response.css("p.prodnavigation.detailprodnavigation a.ectlink::text").getall()
        brand = breadcrumb[1].strip() if len(breadcrumb) > 1 else ""
        model = breadcrumb[2].strip() if len(breadcrumb) > 2 else ""

        part_name = response.css("[itemprop=name]::text").get("").strip()
        description = response.css("[itemprop=description]::text").get("").strip()
        price_raw = response.css("[itemprop=price]::text").get("").strip()
        price = re.sub(r"[^\d.]", "", price_raw) or None

        # Build a descriptive name: "WORCESTER GAS BOILER 24i JUNIOR RSF - AAV - 87161061420"
        if model and part_name:
            name = f"{model} - {part_name}"
        elif brand and part_name:
            name = f"{brand} - {part_name}"
        else:
            name = part_name

        if not name:
            return

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "product": {
                "name": name,
                "brand": brand,
                "description": description,
                "price": price,
                "currency": "GBP",
            },
        }
