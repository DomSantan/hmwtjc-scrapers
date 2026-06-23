import scrapy

SITEMAP_INDEX = "https://www.wolseley.co.uk/sitemap.xml"


class SitemapSpiderWolseley(scrapy.Spider):
    name = "sitemap_spider_wolseley"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_INDEX,
            meta={"impersonate": "chrome120"},
            callback=self.parse_index,
        )

    def parse_index(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap index: {response.status}")
            return
        response.selector.remove_namespaces()
        for loc in response.xpath("//sitemap/loc/text()").getall():
            yield scrapy.Request(
                url=loc.strip(),
                meta={"impersonate": "chrome120"},
                callback=self.parse_sitemap,
            )

    def parse_sitemap(self, response):
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            url = url.strip()
            # Only yield product pages
            if "/product/" in url:
                yield {"url": url}
