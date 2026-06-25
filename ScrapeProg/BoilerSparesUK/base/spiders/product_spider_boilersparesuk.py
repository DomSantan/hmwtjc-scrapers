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
        # Breadcrumb: Home » BRAND » MODEL — brand is index 1
        breadcrumb = response.css("p.prodnavigation.detailprodnavigation a.ectlink::text").getall()
        brand = breadcrumb[1].strip() if len(breadcrumb) > 1 else ""

        # itemprop="name" e.g. "BOILER SECTION - 170070"
        part_name = response.css("[itemprop=name]::text").get("").strip()

        # First text node of description (before <br>) e.g. "Section - Rear - 8218 0051"
        desc_first_line = response.xpath('//*[@itemprop="description"]/text()[1]').get("").strip()

        price_raw = response.css("[itemprop=price]::text").get("").strip()
        price = re.sub(r"[^\d.]", "", price_raw) or None

        # Combined name: "BOILER SECTION - 170070, Section - Rear - 8218 0051"
        if desc_first_line and desc_first_line != part_name:
            name = f"{part_name}, {desc_first_line}"
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
                "price": price,
                "currency": "GBP",
            },
        }
