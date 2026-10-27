import scrapy

PRODUCT_SITEMAP = "https://www.heatandplumb.com/sitemap/google-sitemap-products.xml"


class SitemapSpiderHeatAndPlumb(scrapy.Spider):
    name = "sitemap_spider_heatandplumb"

    # Heat and Plumb blocks requests without a proper Accept header
    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    }

    def start_requests(self):
        yield scrapy.Request(
            url=PRODUCT_SITEMAP,
            meta={"impersonate": "chrome133a"},
            callback=self.parse_sitemap,
        )

    def parse_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        urls = [u.strip() for u in response.xpath("//url/loc/text()").getall()]
        # A ?variation= page's product is already in its parent page's ProductGroup
        # hasVariant (checked 2026-10-27: counts matched exactly), so fetching it again
        # yields nothing new. A 121-long run of these tripped the circuit breaker at
        # ~10.9k items on 2026-10-26. Keep variants only when the parent isn't listed.
        parents = {u for u in urls if "variation=" not in u}
        for url in urls:
            if "variation=" in url and url.split("?")[0] in parents:
                continue
            yield {"url": url}
