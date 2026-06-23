import scrapy
import re

SITEMAP_URL = "https://www.selcobw.com/sitemaps/materials/sitemap.xml"

# Only keep leaf category pages (4+ path segments) — these show product grids
CATEGORY_MIN_DEPTH = 4


class SitemapSpiderSelco(scrapy.Spider):
    name = "sitemap_spider_selco"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_URL,
            meta={"impersonate": "chrome120"},
            callback=self.parse_sitemap,
        )

    def parse_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Sitemap failed: {response.status}")
            return
        response.selector.remove_namespaces()
        seen = set()
        for url in response.xpath("//url/loc/text()").getall():
            url = url.strip()
            # Keep only deep category pages (leaf nodes = actual product listings)
            path = url.replace("https://www.selcobw.com", "")
            if path.count("/") >= CATEGORY_MIN_DEPTH and url not in seen:
                seen.add(url)
                yield {"url": url}
