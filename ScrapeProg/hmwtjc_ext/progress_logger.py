"""
Periodic progress logger for HMWTJC scrapers.

Logs item count, rate, and elapsed time every LOG_EVERY items so the
GitHub Actions log shows the scraper is alive and making progress.

Injected at runtime via override_settings.py — no individual spider
settings.py changes required.
"""
import logging
import time

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)

LOG_EVERY = 500


class ProgressLogger:

    def __init__(self, crawler):
        self.crawler = crawler
        self.last_logged = 0
        self.start_time = None

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("PROGRESS_LOGGER_ENABLED", True):
            raise NotConfigured
        ext = cls(crawler)
        crawler.signals.connect(ext.on_spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.on_item_scraped, signal=signals.item_scraped)
        return ext

    def on_spider_opened(self, spider):
        self.start_time = time.time()

    def on_item_scraped(self, item, response, spider):
        count = self.crawler.stats.get_value("item_scraped_count", 0)
        if count - self.last_logged >= LOG_EVERY:
            self.last_logged = count
            elapsed = time.time() - self.start_time if self.start_time else 0
            rate = count / elapsed if elapsed > 0 else 0
            logger.info(
                f"[progress] {count:,} items scraped "
                f"({rate:.1f}/s, {elapsed / 60:.0f}m elapsed)"
            )
