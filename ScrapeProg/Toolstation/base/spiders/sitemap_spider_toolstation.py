import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_toolstation"

    def start_requests(self):
        yield scrapy.Request(url = "https://www.toolstation.com/sitemap.xml",
                             meta = {"impersonate":"chrome120"},
                             )


    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        product_sitemaps = response.xpath("//sitemap/loc/text()").getall()
        for url in product_sitemaps:
            if 'category' in url:
                yield scrapy.Request(url=url, callback=self.parse_product_sitemap,meta= {"impersonate":"chrome120"})

    def parse_product_sitemap(self,response):
        response.selector.remove_namespaces()
        product_urls = response.xpath("//url/loc/text()").getall()
        for url in product_urls:
            yield {"url":url}




       