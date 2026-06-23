import scrapy
import csv
import json
import re


class GeberitProductSpider(scrapy.Spider):
    name = "product_spider_geberit"

    def start_requests(self):
        with open("url.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url'].strip()
                if url:
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse,
                        meta={"impersonate": "chrome120"},
                    )

    def parse(self, response):
        # The site migrated from Next.js Pages Router to App Router.
        # Product data is now in RSC (React Server Component) flight data —
        # self.__next_f.push([1, "<json-encoded-payload>"]) — not __NEXT_DATA__.
        #
        # Two useful data sources in the RSC payload:
        #   1. schema.org ProductGroup (block with "@type":"ProductGroup") — product name + MPN list
        #   2. productArticlesData — per-article: id, eanCode, description (includes dimensions)

        product_name = None
        articles = []

        for block_raw in re.findall(
            r'self\.__next_f\.push\(\[(.*?)\]\s*\)', response.text, re.DOTALL
        ):
            # Each block is [1, "<escaped-payload>"] — JSON decode it
            try:
                decoded = json.loads('[' + block_raw + ']')
                payload = decoded[1] if isinstance(decoded, list) and len(decoded) > 1 else None
            except (json.JSONDecodeError, IndexError):
                continue

            if not payload or not isinstance(payload, str):
                continue

            # ── Source 1: schema.org ProductGroup (product name) ──────────────
            if '"@type":"ProductGroup"' in payload and not product_name:
                try:
                    schema = json.loads(payload)
                    product_name = schema.get("name")
                except (json.JSONDecodeError, AttributeError):
                    pass

            # ── Source 2: productArticlesData (article details) ───────────────
            if '"productArticlesData"' in payload and not articles:
                start = payload.find('"productArticlesData":{"articles":[')
                if start < 0:
                    continue
                arr_start = payload.find('[', start + len('"productArticlesData":{"articles":'))
                if arr_start < 0:
                    continue

                # Walk forward to find the balanced end of the articles array
                depth = 0
                arr_end = arr_start
                for i, ch in enumerate(payload[arr_start:], arr_start):
                    if ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                        if depth == 0:
                            arr_end = i
                            break

                articles_str = payload[arr_start:arr_end + 1]
                # RSC uses "$undefined" for undefined values — replace with null
                articles_str = articles_str.replace('"$undefined"', 'null')
                # RSC path references start with "$" — replace with null
                articles_str = re.sub(r'"\\?\$[^"]{2,}"', 'null', articles_str)

                try:
                    articles = json.loads(articles_str)
                except json.JSONDecodeError:
                    self.logger.warning(f"Failed to parse articles JSON on {response.url}")
                    continue

            if product_name and articles:
                break

        if not articles:
            self.logger.warning(f"No article data found on {response.url}")
            return

        for article in articles:
            if article.get("archived"):
                continue
            yield {
                "supplier": "Geberit",
                "source_url": response.url,
                "name": article.get("description") or product_name,
                "product_group_name": product_name,
                "article_code": article.get("id"),
                "ean": article.get("eanCode"),
                "buyable_in_webshop": article.get("buyableInWebshop"),
                "make_to_order": article.get("makeToOrder"),
            }
