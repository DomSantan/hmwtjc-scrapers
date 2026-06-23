import scrapy
import csv
import json
import os
from urllib.parse import urlparse


class GeberitDebugSpider(scrapy.Spider):
    name = "product_spider_geberit_debug"

    def start_requests(self):
        with open("url.csv", newline='') as f:
            reader = csv.DictReader(f)
            urls = [row["url"].strip() for row in reader if row["url"].strip()]
            for url in urls[:1]:  # Only take first 30
                yield scrapy.Request(url="https://catalog.geberit.co.uk/en-GB/product/PRO_101559", callback=self.parse)

    def parse(self, response):
        script_data = response.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
        if not script_data:
            self.logger.warning(f"No __NEXT_DATA__ found on {response.url}")
            return

        try:
            json_data = json.loads(script_data)
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse JSON from {response.url}")
            return

        # Extract a safe filename from the product slug
        path = urlparse(response.url).path  # /en-GB/product/PRO_101559
        slug = path.strip("/").split("/")[-1]  # PRO_101559
        filename = f"debug_json/{slug}.json"

        os.makedirs("debug_json", exist_ok=True)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        self.logger.info(f"Saved raw __NEXT_DATA__ to {filename}")
