import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderPlumbworld(scrapy.Spider):
    name = "product_spider_plumbworld"
    supplier_name = "Plumbworld"

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

    def _find_product_ld(self, html):
        """
        Plumbworld uses type='application/ld+json' (single quotes) and embeds
        the Product inside a large list of WebPageElement items. Scan all blocks
        and list items for @type=Product.
        """
        blocks = re.findall(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            html, re.DOTALL
        )
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    return item
        return None

    def _parse_delivery(self, html):
        """
        OG description contains compact stock + delivery info, e.g.:
        'Lowest price guaranteed. In stock: Delivery Next Day. Rated 4.9/5.'
        Also check for free delivery flag in the dataLayer JS.
        """
        og_match = re.search(
            r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html
        )
        if not og_match:
            return None, None

        desc = og_match.group(1)
        in_stock = bool(re.search(r'\bin\s+stock\b', desc, re.IGNORECASE))

        parts = []
        if re.search(r'next.?day', desc, re.IGNORECASE):
            parts.append("Next Day Delivery available")
        if re.search(r'free\s+deliver', desc, re.IGNORECASE):
            parts.append("Free Delivery")
        # Fallback: check dataLayer for free delivery flag
        if not parts:
            free_del = re.search(r'"_conv_free_delivery"\s*:\s*(true|false)', html)
            if free_del and free_del.group(1) == "true":
                parts.append("Free Delivery")
        delivery_info = "; ".join(parts) if parts else None

        return in_stock, delivery_info

    def parse(self, response):
        html = response.text
        product = self._find_product_ld(html)
        if not product:
            return

        in_stock, delivery_info = self._parse_delivery(html)

        images = product.get("image", [])
        if isinstance(images, dict):
            images = [images.get("url", "")]
        elif isinstance(images, str):
            images = [images]
        else:
            images = [img.get("url", img) if isinstance(img, dict) else img for img in images]

        offer = product.get("offers", {})
        if isinstance(offer, list):
            offer = offer[0] if offer else {}

        # Use JSON-LD availability if present, otherwise fall back to OG parse
        availability = offer.get("availability", "")
        if availability:
            in_stock = availability.lower().endswith("instock")
        else:
            availability = None

        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")

        yield {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "product": {
                "name": product.get("name"),
                "description": re.sub(r'\s+', ' ', (product.get("description") or "")).strip(),
                "brand": brand,
                "sku": product.get("sku"),
                "mpn": product.get("mpn"),
                "gtin13": product.get("gtin13"),
                "category": product.get("category"),
                "image_urls": [img for img in images if img],
                "offer_url": urljoin(response.url, offer.get("url", response.url)),
                "price": offer.get("price"),
                "currency": offer.get("priceCurrency", "GBP"),
                "availability": availability,
                "in_stock": in_stock,
                "stock_count": None,
                "delivery_info": delivery_info,
            },
        }
