import scrapy

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_plumbnation"

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.plumbnation.co.uk/sitemap_products.xml",
            meta={"impersonate": "chrome124"},
            headers={"User-Agent": USER_AGENT},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        urls = response.xpath("//url/loc/text()").getall()
        self.logger.info(f"Found {len(urls)} product URLs in sitemap")
        for url in urls:
            yield {"url": url}
