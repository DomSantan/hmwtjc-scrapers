import scrapy


class SitemapSpider(scrapy.Spider):
    name = "sitemap_spider_boilersparesuk"

    def start_requests(self):
        yield scrapy.Request("http://www.boilersparesuk.co.uk/sitemap.xml")

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            if "proddetail.asp" in url:
                yield {"url": url}
