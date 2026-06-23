import scrapy

PRODUCT_SITEMAP = "https://www.heatandplumb.com/sitemap/google-sitemap-products.xml"


class SitemapSpiderHeatAndPlumb(scrapy.Spider):
    name = "sitemap_spider_heatandplumb"

    # Heat and Plumb blocks requests without a proper Accept header
    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    }

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
