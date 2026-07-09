import scrapy

PLUMBING_KEYWORDS = [
    "plumb", "pipe", "fitting", "radiator", "boiler", "drain", "shower",
    "toilet", "cistern", "basin", "bath", "heating", "compression",
    "push-fit", "solder-ring", "end-feed", "copper", "stopcock", "valve",
    "immersion", "cylinder", "inhibitor", "thermostatic", "towel-rail",
    "tap-connector", "tap-valve", "tap-washer", "flexi-hose", "flexi-pipe",
    "waste", "soil", "overflow", "pump", "tank-connector", "water-tank",
    "expansion", "isolation", "solvent-weld", "primaflow",
]


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_wickes"

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.wickes.co.uk/sitemap.xml",
            meta={"impersonate": "chrome120"},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap index: {response.status}")
            return
        response.selector.remove_namespaces()
        for loc in response.xpath("//sitemap/loc/text()").getall():
            if "sitemap-products" in loc:
                yield scrapy.Request(
                    url=loc,
                    callback=self.parse_product_sitemap,
                    meta={"impersonate": "chrome120"},
                )

    def parse_product_sitemap(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch product sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            if any(kw in url.lower() for kw in PLUMBING_KEYWORDS):
                yield {"url": url}
