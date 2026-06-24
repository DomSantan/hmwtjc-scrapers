import scrapy


class UrlGatherSpider(scrapy.Spider):
    name = "url_gather"

    # Seed: top-level building and plumbing category pages.
    # The spider will discover all sub-categories from here.
    start_urls = [
        "https://www.grantandstone.co.uk/building",
        "https://www.grantandstone.co.uk/plumbing",
    ]
    custom_settings = {"DEPTH_LIMIT": 3}

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={"impersonate": "chrome120"},
                                 callback=self.parse_category_index)

    def parse_category_index(self, response):
        """Discover all sub-category links and queue them."""
        links = response.xpath(
            '//a[contains(@href,"/building/") or contains(@href,"/plumbing/")]/@href'
        ).getall()
        seen = set()
        for href in links:
            # Normalise: strip query strings, anchors, trailing slashes
            url = href.split("?")[0].split("#")[0].rstrip("/")
            if url in seen:
                continue
            seen.add(url)
            yield scrapy.Request(
                url + "?product_list_limit=100",
                meta={"impersonate": "chrome120"},
                callback=self.parse_category,
            )

    def parse_category(self, response):
        """Extract product URLs from a category listing page."""
        product_urls = response.xpath(
            '//li[contains(@class,"product-item")]'
            '//a[contains(@class,"product-photo")]/@href'
        ).getall()

        for url in product_urls:
            yield {"url": url}

        # Follow next page if pagination exists
        next_page = response.xpath(
            '//a[@rel="next"]/@href | //li[contains(@class,"pages-item-next")]/a/@href'
        ).get()
        if next_page:
            yield scrapy.Request(
                next_page,
                meta={"impersonate": "chrome120"},
                callback=self.parse_category,
            )
