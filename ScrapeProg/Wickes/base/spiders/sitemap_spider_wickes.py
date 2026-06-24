import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_wickes"

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.wickes.co.uk/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap index: {response.status}")
            return
        response.selector.remove_namespaces()
        # Root is a sitemap index — follow only product sub-sitemaps
        for loc in response.xpath("//sitemap/loc/text()").getall():
            if "sitemap-products" in loc:
                yield scrapy.Request(
                    url=loc,
                    callback=self.parse_product_sitemap,
                    meta={"impersonate": "chrome120"},
                )

    def parse_product_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch product sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
