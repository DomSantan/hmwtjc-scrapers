import re
import scrapy

# Keywords that reliably indicate plumbing/heating/bathroom products.
# Deliberately avoids short ambiguous tokens (e.g. "tap" matches "tape").
PLUMBING_KEYWORDS = [
    "plumb", "pipe", "fitting", "radiator", "boiler", "drain", "soil-pipe",
    "waste-pipe", "waste-trap", "stopcock", "isolation-valve", "ball-valve",
    "compression", "push-fit", "speedfit", "solvent-weld", "copper-tube",
    "shower", "toilet", "cistern", "basin", "bath-trap", "bath-waste",
    "bath-panel", "bath-seal", "immersion", "central-heating", "underfloor",
    "pump", "cylinder", "header-tank", "expansion-vessel", "inhibitor",
    "thermostatic", "rad-valve", "towel-rail", "trv", "tap-connector",
    "tap-valve", "tap-washer", "flexi-hose", "flexi-pipe", "service-valve",
    "gate-valve", "check-valve", "pressure-relief", "float-valve",
]

SITEMAP_BASE = "https://www.diy.com/static/products-sitemap-{}.xml"
# 82 sitemaps in the index — crawl all of them
SITEMAP_COUNT = 82


class SitemapSpiderBandQ(scrapy.Spider):
    name = "sitemap_spider_bandq"

    def start_requests(self):
        for i in range(1, SITEMAP_COUNT + 1):
            yield scrapy.Request(
                url=SITEMAP_BASE.format(i),
                callback=self.parse_sitemap,
                meta={"impersonate": "chrome120"},
            )

    def parse_sitemap(self, response):
        if response.status != 200:
            self.logger.warning(f"Sitemap {response.url} returned {response.status}")
            return

        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            slug = url.lower()
            if any(kw in slug for kw in PLUMBING_KEYWORDS):
                yield {"url": url}
