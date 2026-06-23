"""
Settings overlay injected by run_daily_update.py via SCRAPY_SETTINGS_MODULE.

Chains from each spider's own base.settings (every spider project uses that
module path) and adds the EmptyCircuitBreaker extension. No individual
spider settings.py needs to be touched.

Requires PYTHONPATH to include both:
  - ScrapeProg/            (so hmwtjc_ext is importable)
  - ScrapeProg/<Spider>/   (so base.settings is importable)
"""
import os

from base.settings import *  # noqa: F401, F403

EXTENSIONS = {
    **globals().get("EXTENSIONS", {}),
    "hmwtjc_ext.circuit_breaker.EmptyCircuitBreaker": 900,
    "hmwtjc_ext.progress_logger.ProgressLogger": 901,
}
EMPTY_CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_THRESHOLD", "100"))
