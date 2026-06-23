import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainageonline"

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.drainageonline.co.uk/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()

        product_urls = response.xpath("//url/loc/text()").getall()
        if product_urls:
            for url in product_urls:
                yield {"url": url}
            return

        # Sitemap index — follow sub-sitemaps
        for sm_url in response.xpath("//sitemap/loc/text()").getall():
            yield scrapy.Request(
                url=sm_url,
                callback=self.parse_sub_sitemap,
                meta={"impersonate": "chrome120"},
            )

    def parse_sub_sitemap(self, response):
        if response.status != 200:
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
