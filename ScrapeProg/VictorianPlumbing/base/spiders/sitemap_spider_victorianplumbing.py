import scrapy

# Sitemaps relevant to plumbing/bathroom tradespeople
PLUMBING_SITEMAPS = [
    "basin", "bath-accessories", "bath-panels-and-ends", "bath-screen",
    "bathroom-accessories", "bathroom-suite", "baths", "bidet", "cistern",
    "electric-showers", "heating-accessories", "kitchen-sink",
    "plumbing-supplies", "radiator-valves", "radiators",
    "shower-accessories", "shower-cabin", "shower-door", "shower-enclosure",
    "shower-panel", "shower-parts", "shower-tray", "shower-tray-riser-kit",
    "shower-valve", "special-showers", "tap-handles", "tap-spouts", "taps",
    "thermostatic-shower", "toilet", "toilet-accessories", "toilet-pan",
    "toilet-seat", "towel-rails", "traps-and-wastes", "underfloor-heating",
    "urinal", "wetroom-screens",
]

SITEMAP_INDEX = "https://www.victorianplumbing.co.uk/sitemap.xml"


class SitemapSpiderVictorianPlumbing(scrapy.Spider):
    name = "sitemap_spider_victorianplumbing"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_INDEX,
            meta={"impersonate": "chrome120"},
            callback=self.parse_index,
        )

    def parse_index(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap index: {response.status}")
            return
        response.selector.remove_namespaces()
        for loc in response.xpath("//sitemap/loc/text()").getall():
            slug = loc.split("/")[-1].replace(".xml", "")
            if slug in PLUMBING_SITEMAPS:
                yield scrapy.Request(
                    url=loc,
                    meta={"impersonate": "chrome120"},
                    callback=self.parse_sitemap,
                )

    def parse_sitemap(self, response):
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
