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
import shutil
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
    ("PipeDreamFittings", "PipeDreamFittings", "sitemap_spider_pipedreamfittings",  "url.csv",  "product_spider_pipedream",          "pipedream_products.json", True),
    ("PlasticPipeShop",   "PlasticPipeShop",   "sitemap_spider_plasticpipeshop",    "url.csv",  "product_spider_plasticpipeshop",    "plasticpipeshop.json",    True),
    ("PlumbingSuperstore","PlumbingSuperstore","sitemap_spider_plumbingsuperstore",  "url.csv",  "fetch_products.py",                 "plumbingsuperstore.json", True),
    ("PlumbNation",       "PlumbNation",       "sitemap_spider_plumbnation",        "url.csv",  "fetch_products.py",                 "plumbnation.json",        True),
    ("Screwfix",          "Screwfix",          "sitemap_spider_screwfix",           "url.csv",  "product_spider_screwfix",           "screwfix.json",           False),
    ("Toolstation",       "Toolstation",       "sitemap_spider_toolstation",        "url.csv",  "fetch_products.py",                 "toolstation.json",        True),
    ("VictorianPlumbing", "VictorianPlumbing", "sitemap_spider_victorianplumbing",  "url.csv",  "product_spider_victorianplumbing",  "victorianplumbing.json",  False),
    ("Wickes",            "Wickes",            "sitemap_spider_wickes",             "url.csv",  "fetch_products.py",                 "wickes.json",             True),
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

MONITOR_INTERVAL = 300   # seconds between file-growth checks (5 min)
MAX_STALL_CHECKS  = 3    # consecutive non-growing checks before auto-kill (15 min)


def run_cmd(args, cwd, env=None, label="", timeout=None, monitor_path=None):
    """
    Run a subprocess with real-time stderr streaming and optional file-growth
    monitoring. If monitor_path is set:
      - Logs output file size every 5 minutes.
      - After 3 consecutive checks with no growth (15 min), kills the process
        automatically so a stalled spider doesn't block the rest of the pipeline.
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

        deadline     = (start + timeout) if timeout else None
        last_check   = start
        last_size    = -1
        stall_checks = 0

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
                        stall_checks = 0
                    else:
                        stall_checks += 1
                        remaining = MAX_STALL_CHECKS - stall_checks
                        if stall_checks >= MAX_STALL_CHECKS:
                            proc.kill()
                            proc.wait()
                            stderr_thread.join(timeout=2)
                            elapsed = now - start
                            log.error(
                                f"[{label}] STALLED {stall_checks * MONITOR_INTERVAL // 60}m "
                                f"with no new data ({size_kb:,.0f} KB) — "
                                f"killing and moving on"
                            )
                            return False, elapsed
                        log.warning(
                            f"[{label}] Running {elapsed_min:.0f}m — "
                            f"output NOT growing ({size_kb:,.0f} KB) — "
                            f"possible stall ({remaining} check(s) before auto-kill)"
                        )
                else:
                    stall_checks += 1
                    if stall_checks >= MAX_STALL_CHECKS:
                        proc.kill()
                        proc.wait()
                        stderr_thread.join(timeout=2)
                        elapsed = now - start
                        log.error(
                            f"[{label}] STALLED {stall_checks * MONITOR_INTERVAL // 60}m "
                            f"with no output file — killing and moving on"
                        )
                        return False, elapsed
                    log.warning(
                        f"[{label}] Running {elapsed_min:.0f}m — no output file yet"
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
        [str(VENV_SCRAPY), "crawl", sitemap_spider, "-o", url_csv,
         "-s", "PROGRESS_LOGGER_ENABLED=0"],
        cwd=project_dir, env=scrapy_env, label=label,
        timeout=SITEMAP_TIMEOUT,
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

# ── Per-supplier streaming import ─────────────────────────────────────────────
# After each scraper finishes its JSON is pushed to the data branch and a
# targeted import is dispatched immediately — imports run during the scraping
# window rather than all waiting until every scraper has finished.

_data_branch_lock = threading.Lock()
_data_branch_ready = False
_DATA_BRANCH_DIR   = Path("/tmp/hmwtjc-data-branch")

PRIVATE_REPO = "DomSantan/how-much-will-that-job-cost"
PUBLIC_REPO  = "DomSantan/hmwtjc-scrapers"


def _setup_data_branch(dispatch_pat: str) -> bool:
    global _data_branch_ready
    if _data_branch_ready:
        return True
    result = subprocess.run(
        ["git", "clone", "--branch", "data", "--single-branch", "--depth", "1",
         f"https://x-access-token:{dispatch_pat}@github.com/{PUBLIC_REPO}.git",
         str(_DATA_BRANCH_DIR)],
        capture_output=True,
    )
    if result.returncode != 0:
        log.error(f"Failed to clone data branch: {result.stderr.decode()}")
        return False
    subprocess.run(["git", "config", "user.email", "actions@github.com"], cwd=_DATA_BRANCH_DIR)
    subprocess.run(["git", "config", "user.name", "GitHub Actions"], cwd=_DATA_BRANCH_DIR)
    _data_branch_ready = True
    return True


def push_supplier_and_dispatch(label: str, output_json: str, run_date: str) -> None:
    """Push one supplier's JSON to the data branch then dispatch a targeted import."""
    if not os.getenv("GITHUB_ACTIONS"):
        return
    dispatch_pat = os.getenv("DISPATCH_PAT", "")
    if not dispatch_pat:
        log.warning(f"[{label}] No DISPATCH_PAT — skipping per-supplier import")
        return

    output_path = DATA_DIR / output_json
    if not output_path.exists():
        log.warning(f"[{label}] No output file — skipping import dispatch")
        return

    # Serialise all git operations so concurrent suppliers don't conflict
    with _data_branch_lock:
        if not _setup_data_branch(dispatch_pat):
            return
        subprocess.run(["git", "pull", "--rebase"], cwd=_DATA_BRANCH_DIR, capture_output=True)
        shutil.copy2(output_path, _DATA_BRANCH_DIR / output_json)
        subprocess.run(["git", "add", output_json], cwd=_DATA_BRANCH_DIR)
        commit = subprocess.run(
            ["git", "commit", "-m", f"[{run_date}] Add {label} scrape data"],
            cwd=_DATA_BRANCH_DIR, capture_output=True,
        )
        if commit.returncode != 0:
            log.warning(f"[{label}] Data branch: nothing to commit (file unchanged)")
            return
        push = subprocess.run(["git", "push"], cwd=_DATA_BRANCH_DIR, capture_output=True)
        if push.returncode != 0:
            log.error(f"[{label}] Data branch push failed: {push.stderr.decode()}")
            return
        log.info(f"[{label}] Pushed {output_json} to data branch")

    # Dispatch the per-supplier import workflow (outside the lock — just an HTTP call)
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "-X", "POST",
             f"https://api.github.com/repos/{PRIVATE_REPO}/actions/workflows/daily_import.yml/dispatches",
             "-H", f"Authorization: Bearer {dispatch_pat}",
             "-H", "Accept: application/vnd.github.v3+json",
             "-d", json.dumps({"ref": "main", "inputs": {
                 "run_date": run_date,
                 "supplier": label,
             }})],
            capture_output=True, text=True, timeout=30,
        )
        http_code = result.stdout.strip()
        if http_code == "204":
            log.info(f"[{label}] Per-supplier import dispatched")
        else:
            log.error(f"[{label}] Import dispatch failed (HTTP {http_code})")
    except Exception as e:
        log.error(f"[{label}] Import dispatch error: {e}")


def run_all_scrapers(scrapers, proxy_env, concurrency, run_date):
    """
    Run all scrapers with a sliding window of `concurrency` slots.
    As soon as one scraper finishes another starts — no waiting for a
    full batch to complete before the next begins.
    """
    total = len(scrapers)
    all_results = {}
    dispatch_threads = []

    log.info(f"── Starting {total} scrapers ({concurrency} concurrent) ──")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                run_scraper,
                label, folder, sitemap, csv_name, product, output,
                proxy_env if needs_proxy else None,
                SCRAPER_WORKERS.get(label, 1),
            ): label
            for label, folder, sitemap, csv_name, product, output, needs_proxy in scrapers
        }
        scraper_outputs = {
            label: output
            for label, _, __, ___, ____, output, _____ in scrapers
        }
        for future in as_completed(futures):
            label = futures[future]
            completed = len(all_results) + 1
            try:
                ok, records, elapsed = future.result()
                all_results[label] = (ok, records, elapsed)
                status = "✓" if ok else "✗"
                log.info(
                    f"[{label}] {status} finished in {elapsed / 60:.0f}m — "
                    f"{records:,} records ({completed}/{total} done)"
                )
                if ok:
                    t = threading.Thread(
                        target=push_supplier_and_dispatch,
                        args=(label, scraper_outputs[label], run_date),
                        daemon=False,
                    )
                    t.start()
                    dispatch_threads.append(t)
            except Exception as e:
                log.error(f"[{label}] Uncaught exception: {e}")
                all_results[label] = (False, 0, 0)

    log.info("Waiting for all import dispatches to complete…")
    for t in dispatch_threads:
        t.join(timeout=120)

    passed = [k for k, (ok, *_) in all_results.items() if ok]
    failed = [k for k, (ok, *_) in all_results.items() if not ok]
    log.info(f"── All scrapers done — OK: {passed or 'none'} | Failed: {failed or 'none'} ──")
    return all_results


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
    parser.add_argument("--concurrency",  type=int, default=10,
                        help="Max scrapers running simultaneously (default 10)")
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

    run_date = started_at.strftime("%Y-%m-%d")
    all_results = run_all_scrapers(scrapers_to_run, proxy_env, args.concurrency, run_date)

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
