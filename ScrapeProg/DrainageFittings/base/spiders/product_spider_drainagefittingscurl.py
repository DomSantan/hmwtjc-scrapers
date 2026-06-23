import scrapy
import csv
import re
import json
import random
from curl_cffi.requests import Session


class ProductSpiderSpider(scrapy.Spider):
    name = "product_spider_drainagefittingscurl"
    custom_settings = {
        'DOWNLOAD_HANDLERS': {'http': None, 'https': None},  # Disable Scrapy downloader
    }

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    ]

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row["url"].strip()
                yield scrapy.Request(
                    url=url,
                    callback=self.bypass_with_curl,
                    errback=self.handle_error,
                    dont_filter=True,
                )

    def handle_error(self, failure):
        # Spider design sets DOWNLOAD_HANDLERS to None — all Scrapy requests fail
        # by design. Errors are swallowed here; the stall detector in the
        # orchestrator will kill the spider after 15 min of no output.
        pass

    def bypass_with_curl(self, response):
        url = response.url
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/",
        }

        # Bypass using curl_cffi with JA3 fingerprinting
        session = Session()
        try:
            r = session.get(url, impersonate="chrome120", headers=headers, timeout=20)
            if r.status_code != 200:
                self.logger.warning(f"Failed to fetch {url} with curl_cffi (status {r.status_code})")
                return

            html = r.text

            # Extract gtag data using regex
            match = re.search(r"gtag\('event',\s*'view_item',\s*(\{.*?\})\s*\);", html, re.DOTALL)
            if not match:
                self.logger.warning(f"gtag block not found in {url}")
                return

            raw_json = match.group(1)
            fixed_json = raw_json.replace("'", '"')
            fixed_json = re.sub(r",\s*}", "}", fixed_json)
            fixed_json = re.sub(r",\s*]", "]", fixed_json)

            data = json.loads(fixed_json)
            item = data['items'][0] if 'items' in data and data['items'] else {}

            yield {
                "PageURL": url,
                "ProductID": item.get("item_id"),
                "Name": item.get("item_name"),
                "Brand": item.get("item_brand"),
                "Category": item.get("item_category"),
                "Price": item.get("price"),
                "Currency": data.get("currency")
            }

        except Exception as e:
            self.logger.error(f"curl_cffi request failed for {url}: {e}")
        finally:
            session.close()
