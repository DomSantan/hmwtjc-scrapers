BOT_NAME = "base"
SPIDER_MODULES = ["base.spiders"]
NEWSPIDER_MODULE = "base.spiders"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
ROBOTSTXT_OBEY = False
# Site rebuilt Oct 2026 (~81k /part/ URLs). It answers bursts with HTTP 400: at 16
# concurrent + AutoThrottle, 245/271 sample pages came back 400. A fixed 8 concurrent /
# 0.1s delay returned 204/204 OK, and 3,000 URLs back-to-back ran clean at ~6.5 pages/s,
# so the full catalogue is ~3.5h (cloud job limit raised to 5.5h for it). AutoThrottle off: it ramps past what the site tolerates.
CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 0.1
AUTOTHROTTLE_ENABLED = False
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
