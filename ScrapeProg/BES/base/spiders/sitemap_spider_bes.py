import re
import scrapy


class SitemapSpiderBes(scrapy.Spider):
    name = "sitemap_spider_bes"

    # Product URLs end with a numeric slug, e.g. /angle-washing-machine-tap-15-mm-x-3-4-8137/
    PRODUCT_RE = re.compile(r'-\d+/$')

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.bes.co.uk/media/feeds/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Sitemap fetch failed: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            if self.PRODUCT_RE.search(url):
                yield {"url": url}
