import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "url_gather"

    def start_requests(self):
        for i in range(2):
            yield scrapy.Request(url = f"https://www.grantandstone.co.uk/building/plastics-drainage?p={i}&product_list_limit=100",
                                meta = {"impersonate":"chrome120"},
                                )


    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        product_urls = response.xpath('//div[@class="grid products-grid"]//a[text()="View Product"]/@href').getall()
        for url in product_urls:
            yield {"url":url}

       