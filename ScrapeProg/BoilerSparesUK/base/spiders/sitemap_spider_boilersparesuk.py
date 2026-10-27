import scrapy


class SitemapSpider(scrapy.Spider):
    name = "sitemap_spider_boilersparesuk"

    # Site rebuilt Oct 2026: sitemap.xml is now an index of sitemap-N.xml files and
    # product pages moved from proddetail.asp?prod= to /part/<slug>.
    def start_requests(self):
        yield scrapy.Request("https://boilersparesuk.co.uk/sitemap.xml")

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for child in response.xpath("//sitemapindex/sitemap/loc/text()").getall():
            yield scrapy.Request(child.strip(), callback=self.parse)
        for url in response.xpath("//urlset/url/loc/text()").getall():
            if "/part/" in url:
                yield {"url": url.strip()}
