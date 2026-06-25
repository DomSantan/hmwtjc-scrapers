import csv
import json
import os
import scrapy
import extruct
from w3lib.html import get_base_url
from datetime import datetime


CF_COOKIE_FILE = "cf_cookies.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _cf_cookie_header():
    if os.path.exists(CF_COOKIE_FILE):
        with open(CF_COOKIE_FILE) as f:
            cookies = json.load(f)
        if cookies:
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
    return None


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_plumbnation"
    supplier_name = "PlumbNation"

    def start_requests(self):
        cookie = _cf_cookie_header()
        extra_headers = {"Cookie": cookie, "User-Agent": USER_AGENT} if cookie else {"User-Agent": USER_AGENT}
        with open("url.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome124"},
                        headers=extra_headers,
                    )

    def _parse_images(self, image_field):
        if not image_field:
            return []
        if isinstance(image_field, str):
            return [image_field]
        if isinstance(image_field, dict):
            url = image_field.get("url") or image_field.get("contentUrl", "")
            return [url] if url else []
        if isinstance(image_field, list):
            urls = []
            for img in image_field:
                if isinstance(img, str):
                    urls.append(img)
                elif isinstance(img, dict):
                    u = img.get("url") or img.get("contentUrl", "")
                    if u:
                        urls.append(u)
            return urls
        return []

    def _extract_delivery(self, offer):
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
        if response.status in (403, 503):
            self.logger.warning(f"CF block on {response.url} — skipping")
            return

        base_url = get_base_url(response.text, response.url)
        try:
            metadata = extruct.extract(response.text, base_url=base_url,
                                       syntaxes=["json-ld"], uniform=True)
        except Exception as e:
            self.logger.warning(f"extruct failed on {response.url}: {e}")
            return

        jsonld = metadata.get("json-ld", [])
        product_ld = next((i for i in jsonld if i.get("@type") == "Product"), None)
        if not product_ld:
            return

        offers_raw = product_ld.get("offers", {})
        if isinstance(offers_raw, list):
            offers = offers_raw
        elif isinstance(offers_raw, dict):
            inner = offers_raw.get("offers")
            if inner:
                offers = inner if isinstance(inner, list) else [inner]
            else:
                offers = [offers_raw]
        else:
            offers = []

        images = self._parse_images(product_ld.get("image"))
        brand = (
            product_ld.get("brand", {}).get("name")
            if isinstance(product_ld.get("brand"), dict)
            else product_ld.get("brand")
        )

        for offer in offers:
            avail_raw = offer.get("availability", "")
            availability = "InStock" if "InStock" in avail_raw else "OutOfStock"
            delivery = self._extract_delivery(offer)
            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),
                "product": {
                    "name": product_ld.get("name"),
                    "description": product_ld.get("description", "").strip(),
                    "brand": brand,
                    "mpn": product_ld.get("mpn"),
                    "gtin13": product_ld.get("gtin13"),
                    "sku": product_ld.get("sku"),
                    "image_urls": images,
                    "offer_url": offer.get("url"),
                    "price": offer.get("price") or offer.get("highPrice") or offer.get("lowPrice"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": availability,
                    "stock_count": "",
                    "price_valid_until": offer.get("priceValidUntil"),
                    **delivery,
                },
            }
