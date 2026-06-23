import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_plumbnation"

    def start_requests(self):
        yield scrapy.Request(url = "https://www.plumbnation.co.uk/sitemap.xml",
                             meta = {"impersonate":"chrome120"},
                             )


    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        product_sitemaps = response.xpath("//url/loc/text()").getall()
        for sitemap_url in product_sitemaps:
            yield {"url":sitemap_url}

   




       