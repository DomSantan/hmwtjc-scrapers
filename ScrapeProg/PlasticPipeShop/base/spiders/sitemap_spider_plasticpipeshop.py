import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_plasticpipeshop"

    def start_requests(self):
        # Fails some nights in ~2s with no visible reason (2026-10-24, 10-26): scrapy drops
        # non-200 responses below the WARNING log level the runner shows. Let parse() see
        # every status, and log network errors, so the next failure says why.
        yield scrapy.Request(url = "https://www.plasticpipeshop.co.uk/sitemap.xml",
                             meta = {"impersonate":"chrome133a", "handle_httpstatus_all": True},
                             errback = self.on_error,
                             )

    def on_error(self, failure):
        self.logger.error(f"Failed to fetch sitemap: {failure.getErrorMessage()}")

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: HTTP {response.status} "
                              f"({len(response.body)} bytes) {response.text[:200]!r}")
            return
        response.selector.remove_namespaces()
        product_sitemaps = response.xpath("//url/loc/text()").getall()
        for sitemap_url in product_sitemaps:
            yield {"url":sitemap_url}
