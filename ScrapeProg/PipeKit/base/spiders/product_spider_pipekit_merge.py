import scrapy
import csv
import json
from datetime import datetime


class PipekitMergedSpider(scrapy.Spider):
    name = "product_spider_pipekit_merged"
    supplier_name = "PipeKit"

    def start_requests(self):
        with open("urls.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url:
                    yield scrapy.Request(
                        url=url + ".json",
                        callback=self.parse_product,
                        meta={"impersonate": "chrome120", "source_url": url},
                    )

    def parse_product(self, response):
        if response.status != 200:
            self.logger.warning(f"Non-200 on {response.url}: {response.status}")
            return

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(f"JSON decode failed on {response.url}")
            return

        product = data.get("product")
        if not product:
            return

        source_url = response.meta["source_url"]
        scraped_at = datetime.utcnow().isoformat()
        title = product.get("title", "")
        brand = product.get("vendor", "")
        description = product.get("body_html", "")
        handle = product.get("handle", "")

        images = [img["src"] for img in product.get("images", []) if img.get("src")]

        variants = product.get("variants", [])
        for variant in variants:
            variant_title = variant.get("title", "")
            name = f"{title} - {variant_title}" if variant_title and variant_title != "Default Title" else title

            availability = "InStock" if variant.get("available") else "OutOfStock"
            variant_id = variant.get("id", "")
            offer_url = f"https://www.pipekit.co.uk/products/{handle}?variant={variant_id}" if variant_id else source_url

            yield {
                "supplier": self.supplier_name,
                "source_url": source_url,
                "scraped_at": scraped_at,
                "name": name,
                "description": description,
                "brand": brand,
                "sku": variant.get("sku", ""),
                "image_urls": images,
                "availability": availability,
                "stock_count": "",
                "price": variant.get("price"),
                "currency": "GBP",
                "offer_url": offer_url,
                "variant": variant_title if variant_title != "Default Title" else "",
                "delivery_cutoff": "",
                "delivery_standard_free_threshold": "",
                "delivery_standard_charge": "",
                "delivery_long_free_threshold": "",
                "delivery_long_charge": "",
                "delivery_typical_days": "",
            }
