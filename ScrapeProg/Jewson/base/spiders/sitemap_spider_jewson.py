import scrapy
import re

SITEMAP_INDEX = "https://www.jewson.co.uk/sitemap.xml"


class SitemapSpiderJewson(scrapy.Spider):
    name = "sitemap_spider_jewson"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_INDEX,
            meta={"impersonate": "chrome120"},
            callback=self.parse_index,
        )

    def parse_index(self, response):
        if response.status != 200:
            self.logger.error(f"Sitemap index failed: {response.status}")
            return
        response.selector.remove_namespaces()
        for loc in response.xpath("//sitemap/loc/text()").getall():
            loc = loc.strip()
            if "sitemap_products" in loc:
                yield scrapy.Request(
                    url=loc,
                    meta={"impersonate": "chrome120"},
                    callback=self.parse_sitemap,
                )

    def parse_sitemap(self, response):
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            url = url.strip()
            if "/p/" in url:
                yield {"url": url}
