import scrapy


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_drainagefittings"

    def start_requests(self):
        yield scrapy.Request(url = "https://www.drainagefittings.co.uk/sitemap.xml",
                             meta = {"impersonate":"chrome120"},
                             )


    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            # Keep only 2-segment product paths (e.g. /category/product.html)
            # Exclude static pages, category pages, and /news/ articles
            parts = [p for p in url.split("/") if p and not p.startswith("http")]
            if len(parts) == 2 and not parts[0].startswith("news"):
                yield {"url": url}
                


       