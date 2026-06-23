import scrapy
import csv
import json
import os
from urllib.parse import urlparse


class GeberitDebugSpider(scrapy.Spider):
    name = "product_spider_geberit_debug2"

    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 1.5,
    }

    def start_requests(self):
        with open("url.csv", newline="") as f:
            reader = csv.DictReader(f)
            urls = [row["url"].strip() for row in reader if row["url"].strip()]
            for url in urls[:30]:  # comment says 30, was incorrectly set to 1
                yield scrapy.Request(url="https://catalog.geberit.co.uk/en-GB/product/PRO_101559", callback=self.parse)

    def parse(self, response):
        # ── Strategy 1: classic __NEXT_DATA__ script tag ──────────────────
        script_data = response.xpath('//script[@id="__NEXT_DATA__"]/text()').get()

        if script_data:
            try:
                json_data = json.loads(script_data)
                self._save(response.url, json_data)
                return
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse __NEXT_DATA__ JSON from {response.url}")

        # ── Strategy 2: Next.js moved data to a _next/data/ JSON route ────
        # URL pattern: /en-GB/product/PRO_101559
        # API pattern: /_next/data/<build_id>/en-GB/product/PRO_101559.json
        build_id = self._extract_build_id(response)
        if build_id:
            path = urlparse(response.url).path.rstrip("/")
            api_url = f"https://catalog.geberit.co.uk/_next/data/{build_id}{path}.json"
            self.logger.info(f"Falling back to _next/data route: {api_url}")
            yield scrapy.Request(
                url=api_url,
                callback=self.parse_next_data_json,
                cb_kwargs={"original_url": response.url},
                headers={"Accept": "application/json"},
            )
            return

        self.logger.warning(f"No data source found for {response.url}")

    def _extract_build_id(self, response):
        """Pull the Next.js build ID out of the page's inline __NEXT_DATA__ or meta tag."""
        # Sometimes __NEXT_DATA__ is present but minified differently — try a broad search
        raw = response.xpath('//script[contains(text(),"buildId")]/text()').get()
        if raw:
            try:
                data = json.loads(raw)
                return data.get("buildId")
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback: find it in any script src path like /_next/static/<buildId>/
        src = response.xpath(
            '//script[contains(@src,"/_next/static/")]/@src'
        ).get()
        if src:
            # e.g. /_next/static/abc123XYZ/_buildManifest.js
            parts = src.split("/_next/static/")
            if len(parts) > 1:
                return parts[1].split("/")[0]

        return None

    def parse_next_data_json(self, response, original_url):
        try:
            json_data = json.loads(response.text)
            self._save(original_url, json_data)
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse _next/data JSON for {original_url}")

    def _save(self, url, json_data):
        path = urlparse(url).path
        slug = path.strip("/").split("/")[-1]
        filename = f"debug_json/{slug}.json"
        os.makedirs("debug_json", exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        self.logger.info(f"Saved to {filename}")