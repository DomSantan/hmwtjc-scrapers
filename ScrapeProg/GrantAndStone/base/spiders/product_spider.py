import scrapy
import csv
import re
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_grantandstone"
    supplier_name = "Grant and Stone"

    def start_requests(self):
        with open("drainsurl.csv", "r") as f:
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
        # Name — Magento page-title span, fallback to og:title
        name = response.xpath('//h1[contains(@class,"page-title")]//span/text()').get(default="").strip()
        if not name:
            name = response.xpath('//meta[@property="og:title"]/@content').get(default="").strip()
        if not name:
            return

        # Price — product:price:amount OpenGraph meta (most reliable on Magento)
        price_raw = response.xpath('//meta[@property="product:price:amount"]/@content').get(default="")
        try:
            price = round(float(price_raw), 2) if price_raw else None
        except ValueError:
            price = None

        currency = response.xpath('//meta[@property="product:price:currency"]/@content').get(default="GBP")

        # SKU — itemprop="sku"
        sku = response.xpath('//*[@itemprop="sku"]/text()').get(default="").strip()

        # Description — meta description
        description = response.xpath('//meta[@name="description"]/@content').get(default="").strip()

        # Image — og:image
        image_url = response.xpath('//meta[@property="og:image"]/@content').get(default="")
        image_urls = [image_url] if image_url else []

        # Availability — look for back-in-stock popup (shown when out of stock)
        out_of_stock = bool(response.xpath('//div[@id="back-in-stock-notification-popup"]'))
        availability = "OutOfStock" if out_of_stock else "InStock"

        # Breadcrumb
        breadcrumb_list = [b.strip() for b in response.xpath('//ul[contains(@class,"breadcrumbs")]//li//text()').getall() if b.strip() and b.strip() not in ('/', '>')]

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),

            "product": {
                "name": name,
                "description": description,
                "brand": None,
                "sku": sku,
                "image_urls": image_urls,
                "offer_url": response.url,
                "price": price,
                "currency": currency,
                "availability": availability,
                "stock_count": "",
                "breadcrumb": breadcrumb_list,
                "breadcrumb_str": " > ".join(breadcrumb_list) if breadcrumb_list else None,
            },
        }
