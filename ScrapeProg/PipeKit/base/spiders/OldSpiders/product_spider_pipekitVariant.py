import scrapy
import csv


class OfferDetailsSpider(scrapy.Spider):
    name = "product_spider_pipekitVariant"

    def start_requests(self):
        total = 0
        valid = 0
        with open("PipekitProducts.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                offer_url = row.get("offer_url")
                if offer_url and offer_url.startswith("http"):
                    valid += 1
                    yield scrapy.Request(
                        url=offer_url,
                        callback=self.parse,
                        meta={"sku": row["sku"]},
                        dont_filter=True
                    )
        self.logger.info(f"✅ Total rows: {total} | Offer URLs loaded: {valid}")

    def parse(self, response):
        if response.status != 200:
            self.logger.warning(f"⚠️ Skipped {response.url} — Status {response.status}")
            return

        variant = response.xpath(
            '//div[contains(@class,"product-options-dropdown")]/div[@data-element="current"]/text()'
        ).get()

        price_inc_vat = response.xpath(
            '//dt[contains(text(),"VAT Inc. Price:")]/following::dd[1]/span/text()'
        ).get()

        sku_element = response.xpath(
            '//product-variant-listener[contains(text(),"SKU:")]/text()'
        ).get()

        extra_details = {
            "offer_url": response.url,
            "sku_from_meta": response.meta.get("sku"),
            "Variant": variant.strip() if variant else "",
            "PriceIncVAT": price_inc_vat.strip() if price_inc_vat else "",
            "Sku2": sku_element.replace("SKU:", "").strip() if sku_element else ""
        }

        yield extra_details
