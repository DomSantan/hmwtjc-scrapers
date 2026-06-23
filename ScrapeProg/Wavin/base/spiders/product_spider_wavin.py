import scrapy
import csv
import json
import re
import extruct
from w3lib.html import get_base_url
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_wavin"
    supplier_name = "Wavin"

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

        # Wavin uses ItemPage with mainEntity: Product
        product_ld = None
        for item in jsonld:
            if item.get("@type") == "Product":
                product_ld = item
                break
            if item.get("@type") == "ItemPage":
                main = item.get("mainEntity", {})
                if isinstance(main, dict) and main.get("@type") == "Product":
                    product_ld = main
                    break

        if not product_ld:
            return

        # Identifiers: Catalog Code, EAN Number, SAP number
        identifiers = {}
        for prop in product_ld.get("identifier", []):
            if isinstance(prop, dict):
                identifiers[prop.get("name", "")] = prop.get("value", "")

        # Additional properties (packaging, dimensions)
        extra = {}
        for prop in product_ld.get("additionalProperty", []):
            if isinstance(prop, dict):
                extra[prop.get("name", "")] = prop.get("value", "")

        # Spec table (ETIM classification, dimensions etc)
        spec_table = {}
        for row in response.xpath('//table[contains(@class,"table-fixed")]//tr'):
            key = row.xpath('./td[1]//text()').get(default="").strip()
            val = row.xpath('./td[2]//text() | ./td[2]//span[@class="sr-only"]/text()').get(default="").strip()
            if key and val:
                spec_table[key] = val

        # Image
        img_field = product_ld.get("image", {})
        image_url = img_field.get("url", "") if isinstance(img_field, dict) else (img_field or "")
        image_urls = [image_url] if image_url else []

        # Manufacturer
        mfr = product_ld.get("manufacturer", {})
        manufacturer = mfr.get("name") if isinstance(mfr, dict) else mfr

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),

            "product": {
                "name": product_ld.get("name"),
                "description": product_ld.get("description", "").strip(),
                "category": product_ld.get("category"),
                "manufacturer": manufacturer,
                "catalog_code": identifiers.get("Catalog Code", ""),
                "ean": identifiers.get("EAN Number", ""),
                "sap_number": identifiers.get("SAP number", ""),
                "image_urls": image_urls,
                "price": None,
                "currency": "GBP",
                "availability": "",
                "stock_count": "",
                "packaging": extra,
                "specs": spec_table,
            },
        }
