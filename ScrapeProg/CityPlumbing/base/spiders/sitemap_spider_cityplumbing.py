import scrapy

SITEMAP_URLS = [
    "https://www.cityplumbing.co.uk/sitemap_products.xml",
    "https://www.cityplumbing.co.uk/sitemap_products_1.xml",
]


class SitemapSpiderCityPlumbing(scrapy.Spider):
    name = "sitemap_spider_cityplumbing"

    def start_requests(self):
        for url in SITEMAP_URLS:
            yield scrapy.Request(
                url=url,
                meta={"impersonate": "chrome120"},
                callback=self.parse_sitemap,
            )

    def parse_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.url} ({response.status})")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
