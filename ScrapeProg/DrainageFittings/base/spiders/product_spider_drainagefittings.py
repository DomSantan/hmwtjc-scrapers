import csv
import json
import random
import re
from urllib.parse import urlparse

import scrapy


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
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    headers={
                        "User-Agent": random.choice(self.USER_AGENTS),
                        "Accept-Language": "en-GB,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": "https://www.google.com/",
                    },
                    meta={"impersonate": "chrome120"},
                )

    def parse(self, response):
        # Name-style pages: extract from gtag('event', 'view_item', {...})
        gtag_script = response.xpath('//script[contains(text(), "gtag")]/text()').get()
        if gtag_script:
            match = re.search(
                r"gtag\('event',\s*'view_item',\s*(\{.*?\})\s*\);",
                gtag_script,
                re.DOTALL,
            )
            if match:
                raw = match.group(1).replace("'", '"')
                raw = re.sub(r",\s*}", "}", raw)
                raw = re.sub(r",\s*]", "]", raw)
                try:
                    data = json.loads(raw)
                    item = data["items"][0] if data.get("items") else {}
                    yield {
                        "PageURL": response.url,
                        "ProductID": item.get("item_id"),
                        "Name": item.get("item_name"),
                        "Brand": item.get("item_brand"),
                        "Category": item.get("item_category"),
                        "Price": item.get("price"),
                        "Currency": data.get("currency", "GBP"),
                    }
                    return
                except (json.JSONDecodeError, KeyError):
                    pass

        # SKU-style pages: fall back to JSON-LD Product schema
        for schema_text in response.xpath(
            '//script[@type="application/ld+json"]/text()'
        ).getall():
            try:
                schema = json.loads(schema_text)
            except json.JSONDecodeError:
                continue
            if schema.get("@type") != "Product":
                continue
            offers = schema.get("offers") or {}
            price_raw = offers.get("price")
            path_parts = [p for p in urlparse(response.url).path.split("/") if p]
            category = path_parts[0].replace("-", " ").title() if path_parts else ""
            yield {
                "PageURL": response.url,
                "ProductID": schema.get("sku"),
                "Name": schema.get("name"),
                "Brand": (schema.get("brand") or {}).get("name"),
                "Category": category,
                "Price": float(price_raw) if price_raw is not None else None,
                "Currency": offers.get("priceCurrency", "GBP"),
            }
            return

        self.logger.warning(f"No product data found on {response.url}")
