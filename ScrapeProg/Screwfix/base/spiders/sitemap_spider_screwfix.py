"""
Screwfix sitemap spider.

Handles both sitemap index format (<sitemapindex>) and regular sitemap
format (<urlset>).  Follows child sitemaps before filtering, so we don't
miss categories buried in sub-sitemaps.

Extracts category URLs for the departments we care about and converts each
leaf category slug into a search URL.  The search results pages are what
the product spider reads — they embed an ItemList JSON-LD with product
names, SKUs, prices and images in the SSR HTML (no JS execution required).

Output: url.csv  (one search URL per row)
"""
import scrapy

SITEMAP_INDEX_URL = "https://www.screwfix.com/sitemap-en-gb.xml"

# Departments whose sub-category URLs we want
TARGET_DEPTS = (
    "heating-plumbing",
    "bathrooms-kitchens",
    "electrical",
    "plumbing-drainage",
    "building-materials",
    "fixings-fasteners",
)

# Leaf slugs that are too broad or return irrelevant results
SKIP_LEAF_SLUGS = {
    "bathroom-suites",
    "clearance",
    "new-products",
}


class SitemapSpiderScrewfix(scrapy.Spider):
    name = "sitemap_spider_screwfix"

    def start_requests(self):
        yield scrapy.Request(
            url=SITEMAP_INDEX_URL,
            callback=self.parse_sitemap,
            meta={"impersonate": "chrome120"},
        )

    def parse_sitemap(self, response):
        response.selector.remove_namespaces()

        # Sitemap index — follow each child sitemap
        child_locs = response.xpath("//sitemapindex/sitemap/loc/text()").getall()
        if child_locs:
            for loc in child_locs:
                yield scrapy.Request(
                    url=loc,
                    callback=self.parse_sitemap,
                    meta={"impersonate": "chrome120"},
                )
            return

        # Regular sitemap — extract category URLs
        for url in response.xpath("//urlset/url/loc/text()").getall():
            yield from self._process_url(url)

    def _process_url(self, url):
        # Keep only sub-category URLs under our target departments
        # URL pattern: /c/{dept}/{sub-category}/cat{id}
        if not any(f"/c/{dept}/" in url for dept in TARGET_DEPTS):
            return

        path = url.split("screwfix.com")[-1]
        segments = [s for s in path.split("/") if s and not s.startswith("cat")]
        if not segments:
            return

        leaf_slug = segments[-1]

        # Skip if leaf is a department root (e.g. "heating-plumbing") or a known noise slug
        if leaf_slug in TARGET_DEPTS or leaf_slug in SKIP_LEAF_SLUGS:
            return

        search_term = leaf_slug.replace("-", "+")
        search_url = f"https://www.screwfix.com/search?search={search_term}"
        yield {"url": search_url}
