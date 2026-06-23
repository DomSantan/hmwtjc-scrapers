import scrapy
import csv
from datetime import datetime

BASE_URL = "https://www.plasticpipeshop.co.uk"


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_plasticpipeshop"
    supplier_name = "Plastic Pipe Shop"

    # Site-wide delivery policy (no per-product delivery data available)
    DELIVERY_POLICY = "UK next day delivery"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        product_name = response.xpath('//h1[@class="page_headers"]/text()').get(default="").strip()
        if not product_name:
            return

        description_parts = response.xpath(
            '//div[@class="short-description"]//text() | //div[@id="tab-1"]//text()'
        ).getall()
        description = " ".join(p.strip() for p in description_parts if p.strip())

        sku = response.xpath('//span[@id="product_id"]/text()').get(default="").strip()
        price = response.xpath('//meta[@itemprop="price"]/@content').get(default="")
        currency = response.xpath('//meta[@itemprop="priceCurrency"]/@content').get(default="GBP")
        availability_raw = response.xpath('//meta[@itemprop="availability"]/@content').get(default="")
        availability = "InStock" if "InStock" in availability_raw else "OutOfStock"

        # Full-size product image — href on the MagicZoom link
        image_href = response.xpath('//a[@id="listing_main_image_link"]/@href').get(default="")
        if image_href:
            image_url = image_href if image_href.startswith("http") else BASE_URL + "/" + image_href.lstrip("/")
            image_urls = [image_url]
        else:
            image_urls = []

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),

            "product": {
                "name": product_name,
                "description": description,
                "brand": self.supplier_name,
                "mpn": None,
                "gtin13": None,
                "sku": sku,
                "image_urls": image_urls,
                "offer_url": response.url,
                "price": price,
                "currency": currency,
                "availability": availability,
                "stock_count": "",
                "delivery_policy": self.DELIVERY_POLICY,
            },
        }
