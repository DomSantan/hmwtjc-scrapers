import scrapy

PRODUCT_SITEMAP = "https://www.plumbworld.co.uk/sitemap_products.xml"


class SitemapSpiderPlumbworld(scrapy.Spider):
    name = "sitemap_spider_plumbworld"

    def start_requests(self):
        yield scrapy.Request(
            url=PRODUCT_SITEMAP,
            meta={"impersonate": "chrome120"},
            callback=self.parse_sitemap,
        )

    def parse_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
