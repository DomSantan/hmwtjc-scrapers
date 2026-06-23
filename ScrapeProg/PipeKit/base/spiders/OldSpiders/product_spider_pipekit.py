import scrapy
import csv
import extruct
from w3lib.html import get_base_url
import pandas as pd


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_pipekit"

    def start_requests(self):
        with open("urls.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={"impersonate": "chrome120"},
                )

    def parse(self, response):
        base_url = get_base_url(response.text, response.url)
        metadata = extruct.extract(
            response.text,
            base_url=base_url,
            syntaxes=["json-ld"],
            uniform=True
        )

        jsonld = metadata.get("json-ld", [])

        for item in jsonld:
            if item.get("@type") == "Product":
                # Handle multiple images
                images = item.get("image", [])
                images = images if isinstance(images, list) else [images]

                # Handle multiple offers
                offers = item.get("offers", [])
                offers = offers if isinstance(offers, list) else [offers]

                for offer in offers:
                    yield {
                        "url": response.url,
                        "name": item.get("name"),
                        "sku": item.get("sku"),
                        "description": item.get("description", "").strip(),
                        "brand": item.get("brand", {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
                        "image_urls": "; ".join(images),  # Multiple images concatenated
                        "availability": offer.get("availability"),
                        "price": offer.get("price"),
                        "priceCurrency": offer.get("priceCurrency"),
                        "priceValidUntil": offer.get("priceValidUntil"),
                        "offer_url": offer.get("url"),
                    }
    # df = pd.read_csv("Cleaned_Pipekit_Products.csv")
    # df[["sku", "offer_url"]].dropna().to_csv("offers.csv", index=False)