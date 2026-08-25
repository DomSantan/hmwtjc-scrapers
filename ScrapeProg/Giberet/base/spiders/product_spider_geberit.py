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
        #
        # As of ~2026-08, the site stopped splitting flight data across many small
        # push() calls and now emits one huge push() per page (~200-250KB string).
        # A regex like `\[(.*?)\]\s*\)` isn't string-escape-aware, so against a
        # blob this size it reliably matches some `])` sequence *inside* the
        # escaped string content instead of the real end of the call, truncating
        # the capture and making json.loads() throw on almost every page (only
        # short/simple payloads happened to have their first `])` be the real
        # one, which is why ~20 pages/day were still slipping through). Using
        # json.JSONDecoder().raw_decode() instead lets the JSON parser itself
        # find the correct end of the array, correctly respecting escaped
        # quotes/brackets no matter how large the payload is.
        product_name = None
        articles = []
        decoder = json.JSONDecoder()

        for match in re.finditer(r'self\.__next_f\.push\(', response.text):
            try:
                decoded, _ = decoder.raw_decode(response.text, match.end())
            except json.JSONDecodeError:
                continue

            payload = decoded[1] if isinstance(decoded, list) and len(decoded) > 1 else None

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
