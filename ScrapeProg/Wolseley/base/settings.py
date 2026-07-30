# Scrapy settings for base project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "base"

SPIDER_MODULES = ["base.spiders"]
NEWSPIDER_MODULE = "base.spiders"


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "base (+http://www.yourdomain.com)"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "base.middlewares.BaseSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
# DOWNLOADER_MIDDLEWARES = {
#     # "base.middlewares.BaseDownloaderMiddleware": 543,
#     "base.middlewares.ProxyMiddleware": 300,
# }

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "base.pipelines.BasePipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"


DOWNLOAD_HANDLERS = {
    "http": "scrapy_impersonate.ImpersonateDownloadHandler",
    "https": "scrapy_impersonate.ImpersonateDownloadHandler",
}

# Rate-limit to avoid a sliding-window 429 limiter found 2026-07-30: the
# product step ran fully unthrottled (default CONCURRENT_REQUESTS=16, no
# delay) at ~55-57 items/s, then hit a wall of 429s ~2 min in and never
# recovered for the rest of that run - "Gave up retrying" (3 attempts) on
# ~8,600 URLs out of a 26,418-URL catalogue every single night for at least
# 5 consecutive nights (confirmed via GitHub Actions log history), losing
# roughly a third of the catalogue silently behind a "[Wolseley] finished"
# success line each time. Same AutoThrottle-avoidance lesson as
# PlumbingSuperstore (see that project's settings.py) - flat delay only,
# since AutoThrottle treats DOWNLOAD_DELAY as a floor it speeds past on fast
# responses, not a ceiling.
#
# Calibration (2026-07-30, against the real live site): a quick single-
# threaded burst (30 sequential requests, ~3.3 req/s) and short concurrent
# bursts (4/8/16 at once, not sustained) all came back clean with zero 429s -
# the problem is specifically a *sustained* unthrottled crawl, not a low hard
# ceiling. But real scrapy_impersonate throughput under load ran well below
# the naive CONCURRENT_REQUESTS/DOWNLOAD_DELAY arithmetic (per-request
# overhead dominates): CONCURRENT_REQUESTS=4/DELAY=1.0 only achieved ~0.84
# items/s in a 339-request live test (zero 429s, but too slow - would net
# *fewer* records than today within any reasonable timeout). Bumped to
# CONCURRENT_REQUESTS=8/DELAY=0.4, verified clean again (250-request live
# sample, zero 429s) at ~2.08 items/s - projects to ~3.5h for the full
# 26,418-URL catalogue. PRODUCT_TIMEOUTS entry for Wolseley in
# run_daily_update.py uncapped (was a 4h/14400s hard limit) and added to
# CHECKPOINT_SUPPLIERS to match, since this trades raw speed for completeness
# and may now need close to (or over) the old timeout to finish for real.
# **Not yet verified against a real full-catalogue run on the actual Optiplex
# environment** - check the next nightly run's Wolseley record count and
# "Gave up retrying" count against the 2026-07-30 baseline (16,223 records /
# ~8,598 permanently lost) - if throughput on the real runner differs
# meaningfully from this local calibration, these numbers may need another
# round of tuning (same iterative pattern as the PlumbingSuperstore fix).
CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 0.4
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 20
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]
# ~4 req/s -> 26,418 URLs in ~1.8h, comfortably inside the existing 240m
# product timeout. Not yet verified against a real full-catalogue run -
# check the next nightly run's actual Wolseley record count and "Gave up
# retrying" count against tonight's baseline (16,223 records / ~8,598 lost).

