import json
import os
import scrapy


CF_COOKIE_FILE = "cf_cookies.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _cf_cookie_header():
    if os.path.exists(CF_COOKIE_FILE):
        with open(CF_COOKIE_FILE) as f:
            cookies = json.load(f)
        if cookies:
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
    return None


class SitemapSpiderSpider(scrapy.Spider):
    name = "sitemap_spider_plumbnation"

    def start_requests(self):
        cookie = _cf_cookie_header()
        headers = {"Cookie": cookie, "User-Agent": USER_AGENT} if cookie else {"User-Agent": USER_AGENT}
        yield scrapy.Request(
            url="https://www.plumbnation.co.uk/sitemap.xml",
            meta={"impersonate": "chrome124"},
            headers=headers,
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error(f"Failed to fetch sitemap: {response.status}")
            return
        response.selector.remove_namespaces()
        for url in response.xpath("//url/loc/text()").getall():
            yield {"url": url}
