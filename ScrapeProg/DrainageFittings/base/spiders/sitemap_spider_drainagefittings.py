import scrapy
from urllib.parse import urlparse


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainagefittings"

    def start_requests(self):
        yield scrapy.Request(url="https://www.drainagefittings.co.uk/sitemap.xml",
                             meta={"impersonate": "chrome120"})

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            # Keep only 2-segment product paths (/category/product.html)
            path_parts = [p for p in urlparse(url).path.split("/") if p]
            if len(path_parts) == 2 and path_parts[0] != "news":
                yield {"url": url}
                


       