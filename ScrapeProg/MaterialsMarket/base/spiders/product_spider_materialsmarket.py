import scrapy
import csv
import extruct
from urllib.parse import urljoin
from w3lib.html import get_base_url
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_materialsmarket"
    supplier_name = "Materials Market"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        base_url = get_base_url(response.text, response.url)
        try:
            metadata = extruct.extract(
                        response.text,
                        base_url=base_url,
                        syntaxes=["json-ld"],
                        uniform=True,
                    )
        except Exception as e:
            self.logger.warning(f"extruct failed on {response.url}: {e}")
            return

        jsonld = metadata.get("json-ld", [])
        product_ld = next((i for i in jsonld if i.get("@type") == "Product"), None)
        if not product_ld:
            return

        # Brand — dict or string
        brand = product_ld.get("brand")
        brand_name = brand.get("name") if isinstance(brand, dict) else brand

        # Offers — list or single dict
        offers_raw = product_ld.get("offers", {})
        if isinstance(offers_raw, list):
            offers = offers_raw
        elif isinstance(offers_raw, dict):
            inner = offers_raw.get("offers")
            offers = inner if isinstance(inner, list) else [offers_raw]
        else:
            offers = []

        # Image
        image = product_ld.get("image")
        if isinstance(image, list):
            image_urls = [img if isinstance(img, str) else img.get("url", "") for img in image]
        elif isinstance(image, str):
            image_urls = [image]
        else:
            image_urls = []

        for offer in offers:
            avail = offer.get("availability", "").split("/")[-1]
            offer_url_raw = offer.get("url", "")

            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),

                "product": {
                    "name": product_ld.get("name"),
                    "description": product_ld.get("description", "").strip(),
                    "material": product_ld.get("material"),
                    "brand": brand_name,
                    "manufacturer": product_ld.get("manufacturer"),
                    "mpn": product_ld.get("mpn"),
                    "sku": product_ld.get("sku"),
                    "image_urls": image_urls,
                    "offer_url": urljoin(response.url, offer_url_raw) if offer_url_raw else response.url,
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": avail,
                    "stock_count": "",
                },
            }
