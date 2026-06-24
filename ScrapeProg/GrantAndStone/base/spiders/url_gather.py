import json
import scrapy


GRAPHQL = "https://www.grantandstone.co.uk/graphql"
BASE_URL = "https://www.grantandstone.co.uk"
PAGE_SIZE = 100

QUERY = """
query GetUrls($page: Int!) {
    products(search: "", pageSize: 100, currentPage: $page, sort: {name: ASC}) {
        page_info { total_pages }
        items { url_key }
    }
}
"""


class UrlGatherSpider(scrapy.Spider):
    name = "url_gather"

    def start_requests(self):
        yield self._gql_request(page=1)

    def _gql_request(self, page):
        return scrapy.Request(
            url=GRAPHQL,
            method="POST",
            body=json.dumps({"query": QUERY, "variables": {"page": page}}),
            headers={"Content-Type": "application/json"},
            callback=self.parse,
            cb_kwargs={"page": page},
        )

    def parse(self, response, page):
        data = response.json()["data"]["products"]
        total_pages = data["page_info"]["total_pages"]

        for item in data["items"]:
            yield {"url": f"{BASE_URL}/{item['url_key']}"}

        if page < total_pages:
            yield self._gql_request(page + 1)
