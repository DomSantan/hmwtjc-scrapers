#!/usr/bin/env python3
"""
Daily price refresh pipeline — runs inside hmwtjc-scrapers public repo.

Usage:
  python run_daily_update.py                                    # no-proxy scrapers only
  python run_daily_update.py --proxy-user U --proxy-pass P     # include proxy scrapers
  python run_daily_update.py --batch-size 2 --batch-gap 60     # tune concurrency/delay
  python run_daily_update.py --skip-import                      # scrape only, no DB import
  python run_daily_update.py --only BandQ,Wavin                # specific scrapers only
  python run_daily_update.py --results-file results.json       # write JSON summary
"""

import argparse
import csv
import json
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent.resolve()          # ScrapeProg/
VENV_SCRAPY  = SCRIPT_DIR / "venv" / "bin" / "scrapy"
VENV_PYTHON  = SCRIPT_DIR / "venv" / "bin" / "python"
DATA_DIR     = SCRIPT_DIR.parent / "data"               # hmwtjc-scrapers/data/

# ── Parallel worker counts ────────────────────────────────────────────────────

SCRAPER_WORKERS = {
    "BandQ": 8,
}

# ── Timeouts ──────────────────────────────────────────────────────────────────
# Per-scraper product-step timeout in seconds. Sitemap steps always use
# SITEMAP_TIMEOUT. If a subprocess exceeds its limit it is killed and logged
# as TIMED OUT — the pipeline moves on to the next scraper.

SITEMAP_TIMEOUT = 1800   # 30 min — sitemaps are always quick

PRODUCT_TIMEOUTS = {
    "BandQ":            14400,  # 4 h  — 160k URLs across 8 proxy workers
    "Geberit":          10800,  # 3 h  — large catalogue, slow product pages
    "BES":               9000,  # 2.5 h — 15k URLs, autothrottle can slow to ~2 req/s
    "Screwfix":          7200,  # 2 h  — large catalogue
    "Toolstation":       7200,  # 2 h
    "VictorianPlumbing": 7200,
    "CityPlumbing":      7200,
}
DEFAULT_PRODUCT_TIMEOUT = 5400  # 1.5 h for everything else

# ── Circuit breaker ───────────────────────────────────────────────────────────
# Close a spider after this many consecutive responses that yield no items.
# Indicates an IP block returning blank/redirect pages. 0 = disabled.

CIRCUIT_BREAKER_THRESHOLD = 100

# ── Scraper definitions ───────────────────────────────────────────────────────
# (label, project_folder, sitemap_spider, url_csv, product_spider, output_json, needs_proxy)

SCRAPERS = [
    ("BandQ",             "BandQ",             "sitemap_spider_bandq",              "url.csv",  "product_spider_bandq",              "bandq.json",              True),
    ("BES",               "BES",               "sitemap_spider_bes",                "url.csv",  "product_spider_bes",                "bes.json",                False),
    ("Geberit",           "Giberet",           "sitemap_spider_giberet",            "url.csv",  "product_spider_geberit",            "geberit.json",            False),
    ("Wavin",             "Wavin",             "sitemap_spider_wavin",              "url.csv",  "product_spider_wavin",              "wavin.json",              False),
    ("CityPlumbing",      "CityPlumbing",      "sitemap_spider_cityplumbing",       "url.csv",  "product_spider_cityplumbing",       "cityplumbing.json",       False),
    ("DrainageCentral",   "DrainageCentral",   "sitemap_spider_drainagecentral",    "url.csv",  "product_spider_drainagecentral",    "drainagecentral.json",    False),
    ("DrainageFittings",  "DrainageFittings",  "sitemap_spider_drainagefittings",   "url.csv",  "product_spider_drainagefittingscurl",   "drainagefittings.json",   True),
    ("DrainageOnline",    "DrainageOnline",    "sitemap_spider_drainageonline",     "urls.csv", "product_spider_drainageonline",     "drainageonline.json",     False),
    ("DrainageSuperstore","DrainageSuperstore","sitemap_spider_drainagesuperstore", "urls.csv", "product_spider_drainagesuperstore", "drainagesuperstore.json", False),
    ("GrantAndStone",     "GrantAndStone",     "url_gather",                        "urls.csv", "product_spider",                    "grantandstone.json",      False),
    ("MaterialsMarket",   "MaterialsMarket",   "sitemap_spider_materialsmarket",    "url.csv",  "product_spider_materialsmarket",    "materialsmarket.json",    False),
    ("PipeKit",           "PipeKit",           "sitemap_spider_pipekit",            "urls.csv", "product_spider_pipekit_merged",     "pipekit.json",            False),
    ("PipeDreamFittings", "PipeDreamFittings", "sitemap_spider_pipedreamfittings",  "url.csv",  "product_spider_pipedream",          "pipedream_products.json", False),
    ("PlasticPipeShop",   "PlasticPipeShop",   "sitemap_spider_plasticpipeshop",    "url.csv",  "product_spider_plasticpipeshop",    "plasticpipeshop.json",    False),
    ("PlumbingSuperstore","PlumbingSuperstore","sitemap_spider_plumbingsuperstore",  "url.csv",  "fetch_products.py",                 "plumbingsuperstore.json", False),
    ("PlumbNation",       "PlumbNation",       "sitemap_spider_plumbnation",        "url.csv",  "fetch_products.py",                 "plumbnation.json",        False),
    ("Screwfix",          "Screwfix",          "sitemap_spider_screwfix",           "url.csv",  "product_spider_screwfix",           "screwfix.json",           False),
    ("Toolstation",       "Toolstation",       "sitemap_spider_toolstation",        "url.csv",  "fetch_products.py",                 "toolstation.json",        False),
    ("VictorianPlumbing", "VictorianPlumbing", "sitemap_spider_victorianplumbing",  "url.csv",  "product_spider_victorianplumbing",  "victorianplumbing.json",  False),
    ("Wickes",            "Wickes",            "sitemap_spider_wickes",             "url.csv",  "fetch_products.py",                 "wickes.json",             False),
]

# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def repair_json_array(path: Path) -> bool:
    """
    If a JSON array file was truncated by a hard kill (missing closing ']'),
    repair it in-place so insert_products.py can parse it. Returns True if
    a repair was made.
    """
    try:
        text = path.read_text(errors="replace").strip()
        if not text.startswith("["):
            return False
        try:
            json.loads(text)
            return False  # already valid
        except json.JSONDecodeError:
            pass
        # Strip trailing partial item and comma, then close the array
        # Walk back from the end to find the last complete '}'
        last_brace = text.rfind("}")
        if last_brace == -1:
            return False
        repaired = text[: last_brace + 1] + "\n]"
        try:
            json.loads(repaired)  # verify the repair works
        except json.JSONDecodeError:
            return False
        path.write_text(repaired)
        return True
    except Exception:
        return False


def count_json_records(path: Path) -> int:
    """Count items in a JSON array file, or lines for JSONL. Returns 0 on error."""
    try:
        text = path.read_text(errors="replace").strip()
        if text.startswith("["):
            try:
                return len(json.loads(text))
            except json.JSONDecodeError:
                # Truncated array (e.g. hard-killed process) — count item lines
                return sum(1 for line in text.splitlines()
                           if line.strip().rstrip(",").endswith("}"))
        # JSONL fallback
        return sum(1 for line in text.splitlines() if line.strip().startswith("{"))
    except Exception:
        return 0


def _split_url_csv(csv_path: Path, n: int) -> list:
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    chunk_size = max(1, -(-len(rows) // n))
    chunks = []
    for i in range(n):
        chunk = rows[i * chunk_size:(i + 1) * chunk_size]
        if not chunk:
            break
        path = csv_path.parent / f"_chunk_{i}.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(chunk)
        chunks.append(path)
    return chunks


def _merge_json_outputs(chunk_paths: list, final_path: Path):
    all_items = []
    for path in chunk_paths:
        if not path.exists():
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            all_items.extend(data if isinstance(data, list) else [data])
        except json.JSONDecodeError:
            with open(path) as f:
                for line in f:
                    line = line.strip().rstrip(",")
                    if line and line not in ("[", "]"):
                        try:
                            all_items.append(json.loads(line))
                        except Exception:
                            pass
        path.unlink(missing_ok=True)
    with open(final_path, "w") as f:
        json.dump(all_items, f)
    log.info(f"Merged {len(all_items):,} items from {len(chunk_paths)} workers → {final_path.name}")


def _run_scraper_parallel(label, project_dir, url_csv_name, product_spider,
                          output_path, env, workers, timeout=None):
    url_csv_path = project_dir / url_csv_name
    chunk_csvs = _split_url_csv(url_csv_path, workers)
    actual_workers = len(chunk_csvs)
    log.info(f"[{label}] {actual_workers} parallel workers")
    chunk_outputs = [
        output_path.parent / f"_chunk_{i}_{output_path.name}"
        for i in range(actual_workers)
    ]

    def run_worker(i, chunk_csv, chunk_out):
        ok, t = run_cmd(
            [str(VENV_SCRAPY), "crawl", product_spider,
             "-a", f"url_file={chunk_csv}", "-o", str(chunk_out)],
            cwd=project_dir, env=env, label=f"{label}:w{i}",
            timeout=timeout,
            monitor_path=chunk_out,
        )
        chunk_csv.unlink(missing_ok=True)
        return ok, t

    results = {}
    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
        futures = {pool.submit(run_worker, i, csv, out): i
                   for i, (csv, out) in enumerate(zip(chunk_csvs, chunk_outputs))}
        for future in as_completed(futures):
            i = futures[future]
            ok, t = future.result()
            results[i] = ok
            log.info(f"[{label}:w{i}] {'Done' if ok else 'FAILED'} in {t:.0f}s")

    if not any(results.values()):
        log.error(f"[{label}] All parallel workers failed")
        return False

    existing_outputs = [p for p in chunk_outputs if p.exists()]
    _merge_json_outputs(existing_outputs, output_path)
    return True


# ── Core runner ───────────────────────────────────────────────────────────────

MONITOR_INTERVAL = 300  # seconds between file-growth checks (5 min)


def run_cmd(args, cwd, env=None, label="", timeout=None, monitor_path=None):
    """
    Run a subprocess with real-time stderr streaming and optional file-growth
    monitoring. If monitor_path is set, logs output file size every 5 minutes
    and warns if the file stops growing (possible stall / IP block).
    """
    start = time.time()
    try:
        proc = subprocess.Popen(
            args, cwd=cwd, env=env or os.environ.copy(),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )

        def _stream_stderr():
            for line in proc.stderr:
                log.warning(f"[{label}] {line.rstrip()}")

        stderr_thread = threading.Thread(target=_stream_stderr, daemon=True)
        stderr_thread.start()

        deadline = (start + timeout) if timeout else None
        last_check = start
        last_size = -1

        while True:
            try:
                proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                pass

            now = time.time()

            if deadline and now >= deadline:
                proc.kill()
                proc.wait()
                stderr_thread.join(timeout=2)
                elapsed = now - start
                log.error(
                    f"[{label}] TIMED OUT after {elapsed:.0f}s "
                    f"(limit {timeout // 60}m) — process killed"
                )
                return False, elapsed

            if monitor_path and now - last_check >= MONITOR_INTERVAL:
                p = Path(monitor_path)
                elapsed_min = (now - start) / 60
                if p.exists():
                    size = p.stat().st_size
                    size_kb = size / 1024
                    if size > last_size:
                        log.info(
                            f"[{label}] Running {elapsed_min:.0f}m — "
                            f"output {size_kb:,.0f} KB"
                        )
                        last_size = size
                    else:
                        log.warning(
                            f"[{label}] Running {elapsed_min:.0f}m — "
                            f"output NOT growing ({size_kb:,.0f} KB) — possible stall"
                        )
                else:
                    log.warning(
                        f"[{label}] Running {elapsed_min:.0f}m — "
                        f"no output file yet"
                    )
                last_check = now

        stderr_thread.join(timeout=5)
        elapsed = time.time() - start
        if proc.returncode != 0:
            log.warning(f"[{label}] Non-zero exit {proc.returncode}")
        return proc.returncode == 0, elapsed

    except Exception as e:
        log.error(f"[{label}] Exception: {e}")
        return False, time.time() - start


def _scrapy_env(base_env: dict, project_dir: Path) -> dict:
    """Extend env so the circuit breaker extension is injected into every scrapy run."""
    existing = base_env.get("PYTHONPATH", "")
    parts = [str(SCRIPT_DIR), str(project_dir)]
    if existing:
        parts.append(existing)
    return {
        **base_env,
        "SCRAPY_SETTINGS_MODULE": "hmwtjc_ext.override_settings",
        "CIRCUIT_BREAKER_THRESHOLD": str(CIRCUIT_BREAKER_THRESHOLD),
        "PYTHONPATH": ":".join(parts),
    }


def run_scraper(label, project_folder, sitemap_spider, url_csv, product_spider,
                output_json, proxy_env=None, workers=1):
    """Run the full two-step pipeline for one scraper. Returns (success, record_count, elapsed)."""
    project_dir  = SCRIPT_DIR / project_folder
    url_csv_path = project_dir / url_csv
    output_path  = DATA_DIR / output_json
    base_env     = proxy_env or os.environ.copy()
    scrapy_env   = _scrapy_env(base_env, project_dir)
    product_timeout = PRODUCT_TIMEOUTS.get(label, DEFAULT_PRODUCT_TIMEOUT)
    start = time.time()

    log.info(f"[{label}] Starting sitemap step ({sitemap_spider})")
    if url_csv_path.exists():
        url_csv_path.unlink()

    ok, t = run_cmd(
        [str(VENV_SCRAPY), "crawl", sitemap_spider, "-o", url_csv],
        cwd=project_dir, env=scrapy_env, label=label,
        timeout=SITEMAP_TIMEOUT,
        # no monitor_path — sitemaps are fast, file monitoring not needed
    )
    if not ok:
        log.error(f"[{label}] Sitemap step FAILED after {t:.0f}s — skipping product step")
        return False, 0, time.time() - start

    url_count = 0
    if url_csv_path.exists():
        with open(url_csv_path) as f:
            url_count = max(0, sum(1 for _ in f) - 1)

    if url_count == 0:
        log.error(f"[{label}] URL CSV empty after sitemap step — skipping product step")
        return False, 0, time.time() - start

    log.info(f"[{label}] Sitemap done in {t:.0f}s — {url_count:,} URLs found, "
             f"product timeout {product_timeout // 60}m")

    if output_path.exists():
        output_path.unlink()

    is_py_script = product_spider.endswith(".py")

    if workers > 1 and url_count > workers and not is_py_script:
        log.info(f"[{label}] Starting {workers} parallel workers → {output_json}")
        ok = _run_scraper_parallel(label, project_dir, url_csv, product_spider,
                                   output_path, scrapy_env, workers, product_timeout)
    elif is_py_script:
        log.info(f"[{label}] Starting product step ({product_spider}) → {output_json}")
        ok, t = run_cmd(
            [str(VENV_PYTHON), product_spider, str(output_path)],
            cwd=project_dir, env=base_env, label=label,
            timeout=product_timeout,
            monitor_path=output_path,
        )
        if ok:
            log.info(f"[{label}] Product step done in {t:.0f}s")
        else:
            log.error(f"[{label}] Product step FAILED after {t:.0f}s")
    else:
        log.info(f"[{label}] Starting product step ({product_spider}) → {output_json}")
        ok, t = run_cmd(
            [str(VENV_SCRAPY), "crawl", product_spider, "-o", str(output_path)],
            cwd=project_dir, env=scrapy_env, label=label,
            timeout=product_timeout,
            monitor_path=output_path,
        )
        if ok:
            log.info(f"[{label}] Product step done in {t:.0f}s")
        else:
            log.error(f"[{label}] Product step FAILED after {t:.0f}s")

    records = 0
    if output_path.exists():
        size_kb = output_path.stat().st_size / 1024
        if size_kb < 0.01:
            log.error(f"[{label}] Output is empty — spider yielded no items")
            return False, 0, time.time() - start
        if not ok and repair_json_array(output_path):
            log.warning(f"[{label}] Repaired truncated JSON array — partial data will be imported")
        records = count_json_records(output_path)
        log.info(f"[{label}] Output: {size_kb:.0f} KB — {records:,} records")
    else:
        log.error(f"[{label}] No output file produced")
        return False, 0, time.time() - start

    return ok, records, time.time() - start


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batch(batch, proxy_env, batch_num, total_batches):
    log.info(f"── Batch {batch_num}/{total_batches}: {[s[0] for s in batch]} ──")
    results = {}

    with ThreadPoolExecutor(max_workers=len(batch)) as pool:
        futures = {
            pool.submit(
                run_scraper,
                label, folder, sitemap, csv_name, product, output,
                proxy_env if needs_proxy else None,
                SCRAPER_WORKERS.get(label, 1),
            ): label
            for label, folder, sitemap, csv_name, product, output, needs_proxy in batch
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                results[label] = future.result()  # (ok, records, elapsed)
            except Exception as e:
                log.error(f"[{label}] Uncaught exception: {e}")
                results[label] = (False, 0, 0)

    passed = [k for k, (ok, _, __) in results.items() if ok]
    failed = [k for k, (ok, _, __) in results.items() if not ok]
    log.info(f"── Batch {batch_num} complete — OK: {passed or 'none'} | Failed: {failed or 'none'} ──")
    return results


# ── DB import (local use only — CI uses --skip-import) ───────────────────────

def run_import(db_url):
    log.info("── Running database import (insert_products.py) ──")
    backend_py = SCRIPT_DIR.parent.parent / "backend" / "venv" / "bin" / "python"
    if not backend_py.exists():
        backend_py = Path(sys.executable)
    backend_dir = SCRIPT_DIR.parent.parent / "backend"
    env = {**os.environ.copy(), "DATABASE_URL": db_url}
    ok, t = run_cmd([str(backend_py), "insert_products.py"], cwd=backend_dir, env=env, label="import")
    if not ok:
        log.error(f"Import FAILED after {t:.0f}s")
        return False
    log.info(f"Import complete in {t:.0f}s")
    ok, t = run_cmd([str(backend_py), "scripts/backfill_normalized_tokens.py"],
                    cwd=backend_dir, env=env, label="backfill")
    if ok:
        log.info(f"Backfill complete in {t:.0f}s")
    else:
        log.error(f"Backfill FAILED after {t:.0f}s")
    return ok


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Daily price refresh pipeline")
    parser.add_argument("--proxy-user",   default=os.getenv("proxy_username", ""))
    parser.add_argument("--proxy-pass",   default=os.getenv("proxy_password", ""))
    parser.add_argument("--batch-size",   type=int, default=3)
    parser.add_argument("--batch-gap",    type=int, default=30)
    parser.add_argument("--skip-import",  action="store_true")
    parser.add_argument("--only",         default="")
    parser.add_argument("--db-url",       default="postgresql://postgres:postgres@localhost:5433/howmuchwillthatjobcost")
    parser.add_argument("--results-file", default="", help="Path to write JSON results summary")
    args = parser.parse_args()

    setup_logging()
    started_at = datetime.now(timezone.utc)
    log.info(f"Daily update started — {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if not VENV_SCRAPY.exists():
        log.error(f"Scrapy not found at {VENV_SCRAPY} — run: python -m venv venv && venv/bin/pip install -r requirements.txt")
        sys.exit(1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    proxy_env = None
    if args.proxy_user and args.proxy_pass:
        proxy_env = {**os.environ.copy(), "proxy_username": args.proxy_user, "proxy_password": args.proxy_pass}
        log.info("Proxy credentials provided — proxy scrapers ENABLED")
    else:
        log.info("No proxy credentials — proxy scrapers SKIPPED")

    only_set = {s.strip() for s in args.only.split(",") if s.strip()}
    scrapers_to_run = [
        s for s in SCRAPERS
        if (not only_set or s[0] in only_set)
        and (not s[6] or proxy_env is not None)
    ]
    scrapers_skipped = [
        s for s in SCRAPERS
        if s[6] and proxy_env is None and (not only_set or s[0] in only_set)
    ]

    if not scrapers_to_run and not scrapers_skipped:
        log.warning("No scrapers to run — check --only filter")
        sys.exit(0)

    log.info(f"Running {len(scrapers_to_run)} scrapers: {[s[0] for s in scrapers_to_run]}")
    if scrapers_skipped:
        log.info(f"Skipped (no proxy): {[s[0] for s in scrapers_skipped]}")

    batches = [scrapers_to_run[i:i + args.batch_size] for i in range(0, len(scrapers_to_run), args.batch_size)]
    all_results: dict[str, tuple] = {}  # label → (ok, records, elapsed)

    for i, batch in enumerate(batches, 1):
        batch_results = run_batch(batch, proxy_env, i, len(batches))
        all_results.update(batch_results)
        if i < len(batches):
            log.info(f"Waiting {args.batch_gap}s before next batch…")
            time.sleep(args.batch_gap)

    finished_at = datetime.now(timezone.utc)
    passed  = [k for k, (ok, _, __) in all_results.items() if ok]
    failed  = [k for k, (ok, _, __) in all_results.items() if not ok]
    log.info(f"\n{'='*60}")
    log.info(f"SCRAPING COMPLETE — {len(passed)}/{len(all_results)} succeeded")
    if failed:
        log.warning(f"Failed scrapers: {failed}")

    if not args.skip_import:
        if passed:
            run_import(args.db_url)
        else:
            log.warning("No scrapers succeeded — skipping import")

    # Write structured results JSON
    if args.results_file:
        results_data = {
            "run_date": started_at.strftime("%Y-%m-%d"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_minutes": round((finished_at - started_at).total_seconds() / 60, 1),
            "total_scrapers": len(SCRAPERS),
            "ran": len(all_results),
            "succeeded": len(passed),
            "failed": len(failed),
            "skipped_no_proxy": len(scrapers_skipped),
            "results": {},
        }
        for label, (ok, records, elapsed) in all_results.items():
            results_data["results"][label] = {
                "status": "success" if ok else "failed",
                "records": records,
                "duration_seconds": round(elapsed),
            }
        for s in scrapers_skipped:
            results_data["results"][s[0]] = {
                "status": "skipped",
                "reason": "no proxy credentials",
                "records": 0,
                "duration_seconds": 0,
            }
        Path(args.results_file).write_text(json.dumps(results_data, indent=2))
        log.info(f"Results written to {args.results_file}")

    log.info(f"Pipeline finished — {finished_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")


if __name__ == "__main__":
    main()
