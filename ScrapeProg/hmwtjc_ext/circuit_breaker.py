"""
Empty-page circuit breaker for HMWTJC scrapers.

Closes the spider if a consecutive run of responses yield no items,
which indicates an IP block returning blank/redirect pages rather than
a genuine content gap.

Injected at runtime via -s flags in run_daily_update.py — no individual
spider settings.py changes required.

Settings:
    EMPTY_CIRCUIT_BREAKER_THRESHOLD (int): consecutive empty responses
        before closing. 0 = disabled. Default 0.
"""
import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class EmptyCircuitBreaker:

    def __init__(self, crawler, threshold: int):
        self.crawler = crawler
        self.threshold = threshold
        self.consecutive_empty = 0
        self.last_item_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        threshold = crawler.settings.getint("EMPTY_CIRCUIT_BREAKER_THRESHOLD", 0)
        if not threshold:
            raise NotConfigured
        ext = cls(crawler, threshold)
        crawler.signals.connect(ext.on_item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(ext.on_response_received, signal=signals.response_received)
        return ext

    def on_item_scraped(self, item, response, spider):
        self.consecutive_empty = 0

    def on_response_received(self, response, request, spider):
        current = self.crawler.stats.get_value("item_scraped_count", 0)
        if current > self.last_item_count:
            self.last_item_count = current
            self.consecutive_empty = 0
        else:
            self.consecutive_empty += 1
            if self.consecutive_empty >= self.threshold:
                logger.warning(
                    f"Circuit breaker triggered: {self.consecutive_empty} consecutive "
                    f"responses with no items scraped — possible IP block. "
                    f"Closing spider '{spider.name}'."
                )
                self.crawler.engine.close_spider(spider, "circuit_breaker_empty_responses")
