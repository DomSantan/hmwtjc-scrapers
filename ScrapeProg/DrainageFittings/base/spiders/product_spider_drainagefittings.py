import scrapy
import csv
import re
import json
import random

class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_drainagefittings"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    ]

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                headers = {
                    "User-Agent": random.choice(self.USER_AGENTS),
                    "Accept-Language": "en-GB,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Referer": "https://www.google.com/",
                }
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    headers=headers,
                    meta={"impersonate": "chrome120"},
                )

    def parse(self, response):
        # Extract <script> content containing gtag event
        gtag_script = response.xpath('//script[contains(text(), "gtag")]/text()').get()

        if not gtag_script:
            self.logger.warning(f"No gtag script found on {response.url}")
            return

        match = re.search(r"gtag\('event',\s*'view_item',\s*(\{.*?\})\s*\);", gtag_script, re.DOTALL)
        if not match:
            self.logger.warning(f"gtag block not found on {response.url}")
            return

        raw_json = match.group(1)
        fixed_json = raw_json.replace("'", '"')
        fixed_json = re.sub(r",\s*}", "}", fixed_json)
        fixed_json = re.sub(r",\s*]", "]", fixed_json)

        try:
            data = json.loads(fixed_json)
            item = data['items'][0] if 'items' in data and data['items'] else {}

            yield {
                "PageURL": response.url,
                "ProductID": item.get("item_id"),
                "Name": item.get("item_name"),
                "Brand": item.get("item_brand"),
                "Category": item.get("item_category"),
                "Price": item.get("price"),
                "Currency": data.get("currency")
            }

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parsing error on {response.url}: {e}")
