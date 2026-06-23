import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderWolseley(scrapy.Spider):
    name = "product_spider_wolseley"
    supplier_name = "Wolseley"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={"impersonate": "chrome120"},
                )

    def _extract_delivery(self, html):
        """
        Wolseley's meta description consistently contains delivery info, e.g.:
        'free delivery or click and collect available nationwide.'
        Extract the relevant fragment directly from there.
        """
        meta = re.search(
            r'<meta\s+name="description"\s+content="([^"]+)"', html
        )
        if not meta:
            return None
        desc = meta.group(1)
        # Pull out the delivery/collect clause if present
        m = re.search(
            r'((?:free\s+deliver|next.?day|click\s*(?:&amp;|and)\s*collect)[^.!?]*[.!?]?)',
            desc, re.IGNORECASE
        )
        return m.group(1).strip() if m else None

    def parse(self, response):
        html = response.text
        delivery_info = self._extract_delivery(html)

        ld_scripts = re.findall(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            html, re.DOTALL
        )
        for raw in ld_scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("@type") != "Product":
                continue

            images = data.get("image", [])
            images = images if isinstance(images, list) else [images]

            offer = data.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}

            brand = data.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")

            mpn = data.get("mpn")
            if isinstance(mpn, list):
                mpn = mpn[0] if mpn else None

            availability = offer.get("availability", "")
            in_stock = availability.lower().endswith("instock") if availability else None

            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),
                "product": {
                    "name": data.get("name"),
                    "description": (data.get("description") or "").strip(),
                    "brand": brand,
                    "sku": data.get("sku"),
                    "mpn": mpn,
                    "gtin13": data.get("gtin13"),
                    "category": data.get("category"),
                    "image_urls": images,
                    "offer_url": urljoin(response.url, offer.get("url", response.url)),
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": availability,
                    "in_stock": in_stock,
                    "stock_count": None,
                    "delivery_info": delivery_info,
                },
            }
