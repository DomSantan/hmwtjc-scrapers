import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainagecentral"

    def start_requests(self):
        yield scrapy.Request(url = "https://www.drainagecentral.co.uk/sitemap.xml",
                             meta = {"impersonate":"chrome120"},
                             )


    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            # Category pages end with /; product pages don't
            if not url.rstrip().endswith("/"):
                yield {"url": url}




       