import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainageonline"

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.drainageonline.co.uk/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        response.selector.remove_namespaces()

        product_urls = response.xpath("//url/loc/text()").getall()
        if product_urls:
            for url in product_urls:
                yield {"url": url}
            return

        # Sitemap index — follow sub-sitemaps
        sub_sitemaps = response.xpath("//sitemap/loc/text()").getall()
        if not sub_sitemaps:
            self.logger.error(f"No URLs or sub-sitemaps found (status: {response.status})")
            return
        self.logger.info(f"Sitemap index found — {len(sub_sitemaps)} sub-sitemaps")
        for sm_url in sub_sitemaps:
            yield scrapy.Request(
                url=sm_url,
                callback=self.parse_sub_sitemap,
                meta={"impersonate": "chrome120"},
            )

    def parse_sub_sitemap(self, response):
        response.selector.remove_namespaces()
        urls = response.xpath("//url/loc/text()").getall()
        if not urls:
            self.logger.warning(f"Sub-sitemap empty (status: {response.status}): {response.url}")
        for url in urls:
            yield {"url": url}
