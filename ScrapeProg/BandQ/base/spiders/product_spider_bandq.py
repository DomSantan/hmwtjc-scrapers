import csv
import extruct
from urllib.parse import urljoin
from w3lib.html import get_base_url
from datetime import datetime
import scrapy


class ProductSpiderBandQ(scrapy.Spider):
    name = "product_spider_bandq"
    supplier_name = "B&Q"

    # B&Q delivery policy (standard public rates)
    DELIVERY_POLICY = "Free delivery over £50; standard delivery £5"

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
        if response.status != 200:
            return

        base_url = get_base_url(response.text, response.url)
        metadata = extruct.extract(
            response.text,
            base_url=base_url,
            syntaxes=["json-ld"],
            uniform=True,
        )

        product_ld = next(
            (i for i in metadata.get("json-ld", []) if i.get("@type") == "Product"),
            None,
        )
        if not product_ld:
            return

        # Images
        images = product_ld.get("image", [])
        if isinstance(images, str):
            images = [images]
        elif not isinstance(images, list):
            images = []

        # Offers — B&Q has 3 offers (Click & Collect, In-Store, Home Delivery).
        # Take the Home Delivery offer (availableDeliveryMethod=ParcelService) first,
        # then fall back to any offer with a price.
        offers_raw = product_ld.get("offers", [])
        if isinstance(offers_raw, dict):
            offers_raw = [offers_raw]

        delivery_offer = next(
            (o for o in offers_raw if "ParcelService" in o.get("availableDeliveryMethod", "")),
            offers_raw[0] if offers_raw else {},
        )

        price_raw = delivery_offer.get("price")
        try:
            price = float(price_raw) if price_raw not in (None, "", "null") else None
        except (ValueError, TypeError):
            price = None

        avail = delivery_offer.get("availability", "").split("/")[-1]

        # SKU: B&Q uses "model" for their internal catalog number
        sku = product_ld.get("model") or product_ld.get("sku") or product_ld.get("gtin13")

        # Additional properties → flat dict
        extra = {
            p.get("name", ""): p.get("value", "")
            for p in product_ld.get("additionalProperty", [])
            if isinstance(p, dict)
        }

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),

            "product": {
                "name": product_ld.get("name"),
                "description": product_ld.get("description", "").strip(),
                "brand": extra.get("Brand") or extra.get("Manufacturer"),
                "sku": sku,
                "gtin13": product_ld.get("gtin13"),
                "category": product_ld.get("category"),
                "image_urls": images,
                "offer_url": urljoin(response.url, delivery_offer.get("url") or ""),
                "price": price,
                "currency": delivery_offer.get("priceCurrency", "GBP"),
                "availability": avail,
                "stock_count": "",
                "delivery_policy": self.DELIVERY_POLICY,
            },
        }
