import scrapy
import csv
import json
import re
import html as html_lib
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_pipedream"
    supplier_name = "Pipedream Fittings"

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

    def _parse_graph(self, response):
        """Extract Product + ImageObject entries from JSON-LD @graph blocks."""
        product_ld = None
        images_by_id = {}

        for script in response.xpath('//script[@type="application/ld+json"]/text()').getall():
            try:
                data = json.loads(script)
            except (json.JSONDecodeError, ValueError):
                continue
            graph = data.get("@graph", [])
            for item in graph:
                t = item.get("@type", "")
                types = t if isinstance(t, list) else [t]
                if "Product" in types and product_ld is None:
                    product_ld = item
                if "ImageObject" in types:
                    img_id = item.get("@id", "")
                    url = item.get("contentUrl") or item.get("url", "")
                    if img_id and url:
                        images_by_id[img_id] = url
        return product_ld, images_by_id

    def parse(self, response):
        product_ld, images_by_id = self._parse_graph(response)

        product_name = response.xpath('//h1[contains(@class, "product_title")]/text()').get()
        if not product_name and product_ld:
            product_name = product_ld.get("name", "")
        if not product_name:
            product_name = response.xpath('//div[@id="title-bar"]//h3/text()').get(default="").strip()

        description = response.xpath('//meta[@name="description"]/@content').get(default="").strip()
        if not description and product_ld:
            description = product_ld.get("description", "").strip()

        # SKU — prefer JSON-LD; fall back to sku_wrapper span
        sku = ""
        if product_ld:
            sku = product_ld.get("sku", "")
        if not sku:
            sku_raw = response.xpath('//*[contains(@class,"sku_wrapper")]//span[@class="sku"]/text()').get(default="").strip()
            sku = sku_raw

        category = response.xpath('//ul[@class="breadcrumb"]/li[position()=last()-1]/a/text()').get(default="").strip()
        breadcrumb_list = [b.strip() for b in response.xpath('//ul[@class="breadcrumb"]/li//text()').getall() if b.strip()]

        # Image — resolve @id reference in graph, else use gallery img
        image_urls = []
        if product_ld:
            img_field = product_ld.get("image", {})
            img_id = img_field.get("@id", "") if isinstance(img_field, dict) else ""
            resolved = images_by_id.get(img_id, "")
            if resolved:
                image_urls = [resolved]
        if not image_urls:
            gallery_img = response.xpath(
                '//div[contains(@class, "woocommerce-product-gallery__image")]//img/@src'
            ).get()
            if gallery_img:
                image_urls = [gallery_img]

        # Availability from JSON-LD
        avail_ld = ""
        if product_ld:
            offers_ld = product_ld.get("offers", [])
            if isinstance(offers_ld, list) and offers_ld:
                avail_ld = offers_ld[0].get("availability", "").split("/")[-1]
            elif isinstance(offers_ld, dict):
                avail_ld = offers_ld.get("availability", "").split("/")[-1]

        # --- WooCommerce variations (rendered in HTML) ---
        raw_data = response.xpath('//form[@class="variations_form cart"]/@data-product_variations').get()

        variations = None
        if raw_data:
            try:
                variations = json.loads(html_lib.unescape(raw_data))
            except Exception as e:
                self.logger.warning(f"Malformed variation JSON on {response.url} — falling back to simple product")

        if isinstance(variations, list) and variations:
            for var in variations:
                var_img = (var.get("image") or {}).get("src", "")
                yield {
                    "supplier": self.supplier_name,
                    "source_url": response.url,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "name": product_name,
                    "description": description,
                    "brand": "Pipedream",
                    "category": category,
                    "sku": var.get("sku") or sku,
                    "image_urls": [var_img] if var_img else image_urls,
                    "price": var.get("display_price"),
                    "currency": "GBP",
                    "availability": "InStock" if var.get("is_in_stock") else "OutOfStock",
                    "stock_count": str(var.get("max_qty", "")) if var.get("max_qty") else "",
                    "breadcrumb": breadcrumb_list,
                    "breadcrumb_str": " > ".join(breadcrumb_list) if breadcrumb_list else None,
                }
        else:
            # Simple product (no variations form, or WooCommerce returned false/[])
            # Use inc-VAT price (second bdi) if present
            bdis = response.xpath('//p[contains(@class,"price")]//bdi').getall()
            inc_vat_text = ""
            if len(bdis) >= 2:
                inc_vat_text = re.sub(r'<[^>]+>', '', bdis[1]).strip()
            elif bdis:
                inc_vat_text = re.sub(r'<[^>]+>', '', bdis[0]).strip()

            try:
                price = float(inc_vat_text.replace("£", "").replace(",", ""))
            except ValueError:
                price = None

            availability = avail_ld or "InStock"

            yield {
                "supplier": self.supplier_name,
                "source_url": response.url,
                "scraped_at": datetime.utcnow().isoformat(),
                "name": product_name,
                "description": description,
                "brand": "Pipedream",
                "category": category,
                "sku": sku,
                "image_urls": image_urls,
                "price": price,
                "currency": "GBP",
                "availability": availability,
                "stock_count": "",
                "breadcrumb": breadcrumb_list,
                "breadcrumb_str": " > ".join(breadcrumb_list) if breadcrumb_list else None,
            }
