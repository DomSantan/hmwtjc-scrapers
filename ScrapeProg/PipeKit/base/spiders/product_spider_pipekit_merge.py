import re
import scrapy
import csv
import extruct
from w3lib.html import get_base_url
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
                        url=url,
                        callback=self.parse_product,
                        meta={"impersonate": "chrome120"},
                    )

    def _extract_delivery(self, response):
        delivery = {
            "delivery_cutoff": "",
            "delivery_standard_free_threshold": "",
            "delivery_standard_charge": "",
            "delivery_long_free_threshold": "",
            "delivery_long_charge": "",
            "delivery_typical_days": "",
        }

        cutoff = response.xpath(
            '//h5[contains(@class,"delivery-title") and contains(text(),"Cut-Off")]'
            '/following-sibling::div[1]//p/text()'
        ).get()
        if cutoff:
            match = re.search(r'before\s+([\d.:]+\s*[AP]M)', cutoff, re.IGNORECASE)
            delivery["delivery_cutoff"] = match.group(1).strip() if match else cutoff.strip()[:100]

        rows = response.xpath(
            '//h5[contains(@class,"delivery-title") and contains(text(),"Delivery Charges")]'
            '/following-sibling::div[1]//table//tr'
        )
        below_count = 0
        for row in rows:
            cells = [c.strip() for c in row.xpath('.//td/text()').getall() if c.strip()]
            if len(cells) >= 2:
                threshold_text = cells[0]
                charge_text = cells[1]
                threshold_match = re.search(r'£([\d,]+)', threshold_text)
                threshold_val = threshold_match.group(1).replace(",", "") if threshold_match else ""
                charge_match = re.search(r'£([\d.]+)', charge_text)
                charge_val = charge_match.group(1) if charge_match else ("0" if "free" in charge_text.lower() else charge_text)
                if "below" in threshold_text.lower() and threshold_val:
                    if below_count == 0:
                        delivery["delivery_standard_free_threshold"] = threshold_val
                        delivery["delivery_standard_charge"] = charge_val
                    else:
                        delivery["delivery_long_free_threshold"] = threshold_val
                        delivery["delivery_long_charge"] = charge_val
                    below_count += 1

        typical = response.xpath(
            '//h5[contains(@class,"delivery-title") and contains(text(),"Typical")]'
            '/following-sibling::div[1]//p/text()'
        ).get()
        if typical:
            match = re.search(r'(\d+[-–]\d+)\s*days?', typical, re.IGNORECASE)
            delivery["delivery_typical_days"] = match.group(1) if match else ""

        return delivery

    def parse_product(self, response):
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
        delivery = self._extract_delivery(response)
        scraped_at = datetime.utcnow().isoformat()

        for item in jsonld:
            if item.get("@type") != "Product":
                continue

            images = item.get("image", [])
            images = images if isinstance(images, list) else [images]
            brand = item.get("brand", {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand")

            offers = item.get("offers", [])
            offers = offers if isinstance(offers, list) else [offers]

            for offer in offers:
                offer_url = offer.get("url", "")
                avail = offer.get("availability", "").split("/")[-1]
                sku = item.get("sku", "")

                base_product = {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": scraped_at,
                    "name": item.get("name"),
                    "description": item.get("description", "").strip(),
                    "brand": brand,
                    "sku": sku,
                    "image_urls": images,
                    "availability": avail,
                    "stock_count": "",
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "offer_url": offer_url or response.url,
                    "variant": "",
                    **delivery,
                }

                if offer_url and offer_url.rstrip("/") != response.url.rstrip("/"):
                    yield scrapy.Request(
                        url=offer_url,
                        callback=self.parse_variant,
                        meta={
                            "impersonate": "chrome120",
                            "base_product": base_product,
                        },
                        dont_filter=True,
                    )
                else:
                    yield base_product

    def parse_variant(self, response):
        if response.status != 200:
            yield response.meta["base_product"]
            return

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

        variant_name = response.xpath(
            '//div[contains(@class,"product-options-dropdown")]/div[@data-element="current"]/text()'
        ).get(default="").strip()

        price_inc_raw = response.xpath(
            '//dt[contains(text(),"VAT Inc. Price:")]/following::dd[1]/span/text()'
        ).get(default="").strip()

        sku_text = response.xpath(
            '//product-variant-listener[contains(text(),"SKU:")]/text()'
        ).get(default="")

        price_inc = price_inc_raw.replace("£", "").replace(",", "").strip() if price_inc_raw else ""
        sku2 = sku_text.replace("SKU:", "").strip() if sku_text else ""

        jsonld_overrides = {}
        for item in jsonld:
            if item.get("@type") != "Product":
                continue
            images = item.get("image", [])
            images = images if isinstance(images, list) else [images]
            offers = item.get("offers", [])
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                avail = offer.get("availability", "").split("/")[-1]
                jsonld_overrides = {
                    "name": item.get("name") or response.meta["base_product"]["name"],
                    "availability": avail,
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "image_urls": images,
                }
            break

        product = {**response.meta["base_product"]}
        product.update(jsonld_overrides)
        product.update(self._extract_delivery(response))

        if sku2:
            product["sku"] = sku2
        if price_inc:
            product["price"] = price_inc
        if variant_name:
            product["variant"] = variant_name

        yield product
