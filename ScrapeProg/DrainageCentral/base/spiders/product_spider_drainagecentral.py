import re
import scrapy
import csv
import json
import extruct
from w3lib.html import get_base_url
from datetime import datetime


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_drainagecentral"
    supplier_name = "Drainage Central"

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

    def _extract_delivery(self, response):
        """Extract delivery info from the standard DrainageCentral delivery section."""
        delivery = {
            "delivery_estimated": "",
            "delivery_window": "07:30 - 18:00",   # stated on every page
            "delivery_free_threshold_gbp_ex_vat": "",
            "delivery_thresholds": [],
        }

        # Estimated delivery — target the div directly (not script blocks)
        est_texts = response.xpath(
            '//div[@id="DefaultProductDetail-EstimatedDeliveryMessage"]//text()'
        ).getall()
        est = " ".join(t.strip() for t in est_texts if t.strip())
        est = re.sub(r'^Est\.?\s*Delivery\s*', '', est, flags=re.IGNORECASE).strip()
        delivery["delivery_estimated"] = est

        # General free delivery threshold (first "Orders over £X" pattern, no brand prefix)
        all_text = " ".join(response.xpath(
            '//h3[contains(text(),"Delivery Charges")]/following-sibling::*//text()'
        ).getall())

        general = re.search(r'(?:^|[^a-zA-Z])Orders over\s*£([\d,]+)\s*\(Ex VAT\)', all_text)
        if general:
            delivery["delivery_free_threshold_gbp_ex_vat"] = general.group(1).replace(",", "")

        # Brand-specific thresholds
        brand_thresholds = re.findall(
            r'([A-Za-z][A-Za-z0-9/ &,]+(?:Ranges?|Range))\s*[-–]\s*Orders over\s*£([\d,]+)\s*\(Ex VAT\)',
            all_text, re.IGNORECASE
        )
        for brand, amount in brand_thresholds:
            delivery["delivery_thresholds"].append({
                "brand": brand.strip(),
                "free_above_gbp_ex_vat": int(amount.replace(",", "")),
            })

        return delivery

    def parse(self, response):
        base_url = get_base_url(response.text, response.url)
        try:
            metadata = extruct.extract(
                        response.text,
                        base_url=base_url,
                        syntaxes=["json-ld"],
                        uniform=True
                    )
        except Exception as e:
            self.logger.warning(f"extruct failed on {response.url}: {e}")
            return
        jsonld = metadata.get("json-ld", [])

        product_ld = next((i for i in jsonld if i.get("@type") == "Product"), None)
        if not product_ld:
            return

        images = product_ld.get("image", [])
        images = images if isinstance(images, list) else [images]
        delivery = self._extract_delivery(response)

        base = {
            "supplier": self.supplier_name,
            "source_url": response.url,
            "scraped_at": datetime.utcnow().isoformat(),
            "name": product_ld.get("name"),
            "description": product_ld.get("description", "").strip(),
            "brand": (product_ld.get("brand") or {}).get("name")
                     if isinstance(product_ld.get("brand"), dict)
                     else product_ld.get("brand"),
            "mpn": product_ld.get("mpn"),
            "gtin13": product_ld.get("gtin13"),
            "sku": product_ld.get("sku"),
            "image_urls": images,
            "delivery_estimated": delivery["delivery_estimated"],
            "delivery_window": delivery["delivery_window"],
            "delivery_free_threshold_gbp_ex_vat": delivery["delivery_free_threshold_gbp_ex_vat"],
        }

        # Collect variant options from all select dropdowns
        variant_options = []
        selects = response.xpath('//select[starts-with(@id,"variant_")]')
        for sel in selects:
            options = sel.xpath('.//option[@value!=""]/@value').getall()
            variant_options.append(options)

        if not variant_options or not variant_options[0]:
            # No variants — use JSON-LD offer directly
            offers = product_ld.get("offers", {})
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                availability = offer.get("availability", "")
                yield {
                    **base,
                    "price": offer.get("price"),
                    "currency": offer.get("priceCurrency", "GBP"),
                    "availability": availability.split("/")[-1] if availability else "",
                    "stock_count": "",
                    "variant": "",
                    "offer_url": offer.get("url"),
                }
        else:
            # Has variants — fetch price/stock for each via AJAX endpoint
            prod_id_match = re.search(r'changePrice\([^,]+,\s*\d+,\s*(\d+)', response.text)
            prod_id = prod_id_match.group(1) if prod_id_match else ""

            # Generate variant combinations (first dropdown only for now; extend if needed)
            for option in variant_options[0]:
                yield scrapy.FormRequest(
                    url="https://www.drainagecentral.co.uk/default_price_url.php",
                    formdata={"ProdID": prod_id, "firstvariant": option},
                    callback=self.parse_variant,
                    meta={
                        "impersonate": "chrome120",
                        "base": base,
                        "variant": option,
                    },
                    headers={"Referer": response.url},
                )

    def parse_variant(self, response):
        """Parse the #-delimited AJAX response for a variant.

        Response format (from JS source):
          temp[0]  = price (inc or ex VAT depending on temp[1])
          temp[1]  = vat type: 'incvat' | 'exvat' | 'novat'
          temp[2]  = price inc VAT
          temp[3]  = price ex VAT
          temp[4]  = stock count (0 = out of stock)
          temp[5]  = image ID
        """
        base = response.meta["base"]
        variant = response.meta["variant"]
        parts = response.text.strip().split("#")

        price = ""
        stock_count = ""
        availability = ""

        if len(parts) >= 5:
            raw_price = parts[0].strip()
            inc_vat = parts[2].strip()
            ex_vat = parts[3].strip()
            stock_raw = parts[4].strip()

            # Prefer inc-VAT price; fall back to the main price field
            price = inc_vat if inc_vat and inc_vat != "0.00" else (raw_price if raw_price != "0.00" else "")

            if stock_raw and stock_raw != "0":
                stock_count = stock_raw
                availability = "InStock"
            else:
                availability = "OutOfStock"

        yield {
            **base,
            "price": price,
            "currency": "GBP",
            "availability": availability,
            "stock_count": stock_count,
            "variant": variant,
            "offer_url": base["source_url"],
        }
