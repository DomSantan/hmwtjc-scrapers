import scrapy
import csv
import extruct
from urllib.parse import urljoin
from w3lib.html import get_base_url
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_plumbingsuperstore"
    supplier_name = "Plumbing Superstore"

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

    def _extract_delivery(self, offer):
        """Pull delivery info out of an offer's shippingDetails block."""
        sd = offer.get("shippingDetails", {})
        if not sd:
            return {}
        rate = sd.get("shippingRate", {})
        dt = sd.get("deliveryTime", {})
        handling = dt.get("handlingTime", {})
        transit = dt.get("transitTime", {})
        return {
            "delivery_free": rate.get("value") == 0,
            "delivery_charge_gbp": rate.get("value") if rate.get("value") != 0 else None,
            "delivery_handling_days_min": handling.get("minValue"),
            "delivery_handling_days_max": handling.get("maxValue"),
            "delivery_transit_days_min": transit.get("minValue"),
            "delivery_transit_days_max": transit.get("maxValue"),
        }

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

        for item in jsonld:
            if item.get("@type") != "Product":
                continue

            base_name = item.get("name")
            description = item.get("description", "").strip()
            brand = (
                item.get("brand", {}).get("name")
                if isinstance(item.get("brand"), dict)
                else item.get("brand")
            )
            mpn = item.get("mpn")
            sku = item.get("sku")

            images = item.get("image", [])
            if isinstance(images, dict):
                images = [images.get("contentUrl", "")]
            elif isinstance(images, list):
                images = [
                    img.get("contentUrl", "") if isinstance(img, dict) else img
                    for img in images
                ]
            elif isinstance(images, str):
                images = [images]

            # AggregateOffer wrapper → inner offers list
            offers = item.get("offers", {}).get("offers", [])
            for offer in offers:
                avail = offer.get("availability", "").split("/")[-1]
                offer_url_raw = offer.get("url", "")
                delivery = self._extract_delivery(offer)

                yield {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": datetime.utcnow().isoformat(),

                    "product": {
                        "name": base_name,
                        "description": description,
                        "brand": brand,
                        "mpn": mpn,
                        "sku": sku,
                        "image_urls": images,
                        "variant_name": offer.get("name"),
                        "variant_sku": offer.get("sku"),
                        "variant_mpn": offer.get("mpn"),
                        "price": offer.get("highPrice") or offer.get("lowPrice"),
                        "currency": offer.get("priceCurrency", "GBP"),
                        "availability": avail,
                        "stock_count": "",
                        "offer_url": urljoin(response.url, offer_url_raw) if offer_url_raw else response.url,
                        **delivery,
                    }
                }
