import scrapy
import csv
import json
import re
from datetime import datetime
from urllib.parse import urljoin


class ProductSpiderBetterBathrooms(scrapy.Spider):
    name = "product_spider_betterbathrooms"
    supplier_name = "Better Bathrooms"

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

    def _find_product_graph(self, html):
        """Product data lives inside an @graph array in a ld+json block."""
        blocks = re.findall(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            html, re.DOTALL
        )
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            graph = data.get("@graph") if isinstance(data, dict) else None
            if not graph:
                continue
            for item in graph:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    return item
        return None

    def _extract_delivery(self, html):
        """
        Extract per-product delivery info from JS dataLayer variables.
        nextDayDelivery flag + site-wide free delivery threshold from CSS content.
        """
        parts = []
        # Check per-product next-day flag
        ndd = re.search(r"'nextDayDelivery'\s*:\s*'(True|False)'", html, re.IGNORECASE)
        if ndd and ndd.group(1).lower() == "true":
            parts.append("Next Day Delivery available")
        # Site-wide free delivery threshold
        threshold = re.search(r'content:\s*["\']available on orders over (£\d+)["\']', html)
        if threshold:
            parts.append(f"Free delivery on orders over {threshold.group(1)}")
        else:
            # Fallback from meta description
            meta = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
            if meta and "free delivery" in meta.group(1).lower():
                parts.append("Free delivery available")
        return "; ".join(parts) if parts else "Free delivery available"

    def _extract_stock(self, html):
        """Extract stockStatus from dataLayer JS variables."""
        m = re.search(r"'stockStatus'\s*:\s*'([^']+)'", html)
        if m:
            status = m.group(1).lower()
            return status == "instock"
        return None

    def parse(self, response):
        html = response.text
        product = self._find_product_graph(html)
        if not product:
            return

        images = product.get("image", [])
        if isinstance(images, str):
            images = [images]
        elif not isinstance(images, list):
            images = []

        offer = product.get("offers", {})
        if isinstance(offer, list):
            offer = offer[0] if offer else {}

        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")

        in_stock = self._extract_stock(html)

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
                "color": product.get("color"),
                "material": product.get("material"),
                "category": None,
                "image_urls": images,
                "offer_url": response.url,
                "price": offer.get("price"),
                "currency": offer.get("priceCurrency", "GBP"),
                "availability": None,
                "in_stock": in_stock,
                "stock_count": None,
                "delivery_info": self._extract_delivery(html),
            },
        }
