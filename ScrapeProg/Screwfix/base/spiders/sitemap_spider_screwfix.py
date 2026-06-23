"""
Screwfix sitemap spider.

Reads the Screwfix sitemap, extracts all category URLs for the departments
we care about (heating-plumbing, bathrooms-kitchens), and converts each
category slug into a search URL.  The search results pages are what the
product spider reads — they embed an ItemList JSON-LD with product names,
SKUs, prices and images in the SSR HTML (no JavaScript execution required).

Output: url.csv  (one search URL per row)
"""
import re
import scrapy

SITEMAP_URL = "https://www.screwfix.com/sitemap-en-gb.xml"

# Top-level departments whose category URLs we want to turn into searches
TARGET_DEPTS = ("heating-plumbing", "bathrooms-kitchens")

# Category slugs that are too broad to search usefully (return irrelevant results)
SKIP_SLUGS = {"heating-plumbing", "bathrooms-kitchens", "bathroom-suites"}


class SitemapSpiderScrewfix(scrapy.Spider):
    name = "sitemap_spider_screwfix"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_URL,
            callback=self.parse,
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            # Keep only category URLs in our target departments
            if not any(f"/c/{dept}/" in url for dept in TARGET_DEPTS):
                continue

            # Extract the leaf category slug (last path segment before the cat ID)
            # e.g. /c/heating-plumbing/radiators/cat830960 → "radiators"
            path = url.split("screwfix.com")[-1]
            segments = [s for s in path.split("/") if s and not s.startswith("cat")]
            if not segments:
                continue

            leaf_slug = segments[-1]  # e.g. "push-fit-fittings"
            if leaf_slug in SKIP_SLUGS:
                continue

            # Convert hyphen-slug to a search query string
            search_term = leaf_slug.replace("-", "+")
            search_url = f"https://www.screwfix.com/search?search={search_term}"
            yield {"url": search_url}
