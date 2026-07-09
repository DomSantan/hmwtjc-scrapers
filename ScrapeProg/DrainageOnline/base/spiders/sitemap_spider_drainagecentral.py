import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainageonline"

    custom_settings = {
        "DOWNLOAD_TIMEOUT": 90,
    }

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.drainageonline.co.uk/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        if response.status not in (200, 202):
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()

        product_urls = response.xpath("//url/loc/text()").getall()
        if product_urls:
            for url in product_urls:
                yield {"url": url}
            return

        # Sitemap index — follow sub-sitemaps
        sub_sitemaps = response.xpath("//sitemap/loc/text()").getall()
        self.logger.info(f"Sitemap index found — {len(sub_sitemaps)} sub-sitemaps")
        for sm_url in sub_sitemaps:
            yield scrapy.Request(
                url=sm_url,
                callback=self.parse_sub_sitemap,
                meta={"impersonate": "chrome120"},
            )

    def parse_sub_sitemap(self, response):
        if response.status not in (200, 202):
            self.logger.warning(f"Sub-sitemap returned {response.status}: {response.url}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
