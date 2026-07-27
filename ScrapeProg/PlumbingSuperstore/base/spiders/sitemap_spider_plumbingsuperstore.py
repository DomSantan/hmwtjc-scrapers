import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_plumbingsuperstore"

    def start_requests(self):
        yield scrapy.Request(url = "https://www.plumbingsuperstore.co.uk/sitemap/brands.xml",
                             meta = {"impersonate":"chrome133a"},
                             )


    def parse(self, response):
        response.selector.remove_namespaces()
        product_sitemaps = response.xpath("//sitemap/loc/text()").getall()
        if not product_sitemaps:
            self.logger.error(f"No sitemap URLs found (status: {response.status})")
            return
        for sitemap_url in product_sitemaps:
            yield scrapy.Request(url=sitemap_url, callback=self.parse_product_sitemap, meta={"impersonate": "chrome133a"})

    def parse_product_sitemap(self,response):
        response.selector.remove_namespaces()
        product_urls = response.xpath("//url/loc/text()").getall()
        for url in product_urls:
            yield {"url":url}




       