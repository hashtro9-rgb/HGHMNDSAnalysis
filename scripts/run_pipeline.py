"""run_pipeline.py - runs 01_scrape -> 02_clean -> 03_eda -> 04_export_json ->
05_notify in sequence. Logs everything to logs/pipeline_[timestamp].log
(mirrored to console), archives data/cleaned/ into data/archive/week_[ts]/,
prunes old archives beyond KEEP_WEEKS, and writes logs/pipeline_status.json
for 05_notify.py to read. Never crashes silently -- every stage is wrapped.
"""
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

LOGS_DIR = ROOT / settings.LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOGS_DIR / f"pipeline_{TIMESTAMP}.log"
STATUS_FILE = LOGS_DIR / "pipeline_status.json"

PYTHON = sys.executable
STEPS = ["01_scrape.py", "02_clean.py", "03_eda.py", "04_export_json.py", "05_notify.py"]


class Tee:
    """Writes to both a file and the original stream simultaneously."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def run_step(name):
    """Run one pipeline script via subprocess. Returns (status, duration)."""
    path = ROOT / "scripts" / name
    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, str(path)], cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=3600,
        )
        duration = time.time() - start
        print(result.stdout)
        if result.returncode == 0:
            return "success", duration
        print(f"[!] {name} exited with code {result.returncode}")
        return "failed", duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        print(f"[!] {name} timed out after {duration:.0f}s")
        return "failed", duration
    except Exception as e:
        duration = time.time() - start
        print(f"[!] {name} raised an exception: {e}")
        return "failed", duration


def archive_cleaned_data():
    """Copy data/cleaned/ into data/archive/week_[timestamp]/, then prune
    archives beyond KEEP_WEEKS (keeps the N most recent week_* folders)."""
    try:
        cleaned_dir = ROOT / settings.CLEANED_DIR
        archive_dir = ROOT / settings.ARCHIVE_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        if not cleaned_dir.exists():
            print("[archive] data/cleaned/ does not exist yet -- skipping archive.")
            return
        dest = archive_dir / f"week_{TIMESTAMP}"
        shutil.copytree(cleaned_dir, dest)
        print(f"[archive] Copied data/cleaned/ -> {dest}")

        weeks = sorted([d for d in archive_dir.iterdir() if d.is_dir() and d.name.startswith("week_")],
                       key=lambda d: d.name, reverse=True)
        for old in weeks[settings.KEEP_WEEKS:]:
            shutil.rmtree(old, ignore_errors=True)
            print(f"[archive] Pruned old archive: {old.name}")
    except Exception as e:
        print(f"[!] Archiving failed (non-fatal): {e}")


def main():
    log_f = open(LOG_FILE, "w", encoding="utf-8")
    real_stdout = sys.stdout
    sys.stdout = Tee(real_stdout, log_f)

    try:
        header = f"=== HGHMNDS Weekly Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
        print(header)
        print(f"Log file: {LOG_FILE}\n")

        pipeline_start = time.time()
        steps_result = []
        stop_data_steps = False
        DATA_STEPS = [s for s in STEPS if s != "05_notify.py"]

        # Run the data steps (scrape/clean/eda/export) first.
        for name in DATA_STEPS:
            if stop_data_steps:
                print(f"\n>>> Skipping {name} (earlier step failed)")
                steps_result.append({"name": name, "status": "skipped", "duration": 0})
                continue

            print(f"\n>>> Running {name} ...")
            status, duration = run_step(name)
            steps_result.append({"name": name, "status": status, "duration": duration})
            print(f">>> {name}: {status.upper()} ({duration:.1f}s)")

            if status == "failed":
                stop_data_steps = True

        archive_cleaned_data()

        # Write status BEFORE running 05_notify.py so it reports on *this*
        # run's own step results, not whatever was left over from last time.
        interim_runtime = time.time() - pipeline_start
        overall_status = "failure" if any(s["status"] == "failed" for s in steps_result) else "success"
        status_payload = {
            "run_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runtime_seconds": interim_runtime,
            "overall_status": overall_status,
            "steps": steps_result,
            "log_file": str(LOG_FILE),
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_payload, f, indent=2)

        # 05_notify.py always runs, even after a failure above.
        print("\n>>> Running 05_notify.py ...")
        status, duration = run_step("05_notify.py")
        steps_result.append({"name": "05_notify.py", "status": status, "duration": duration})
        print(f">>> 05_notify.py: {status.upper()} ({duration:.1f}s)")

        total_runtime = time.time() - pipeline_start
        overall_status = "failure" if any(
            s["status"] == "failed" for s in steps_result if s["name"] != "05_notify.py") else "success"

        # Rewrite with the final complete record (now including notify itself).
        status_payload.update({
            "runtime_seconds": total_runtime,
            "overall_status": overall_status,
            "steps": steps_result,
        })
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_payload, f, indent=2)

        print("\n" + "=" * 60)
        print("PIPELINE SUMMARY")
        print("=" * 60)
        print(f"{'Step':<22} {'Status':<10} {'Duration':>10}")
        for s in steps_result:
            icon = "PASS" if s["status"] == "success" else ("SKIP" if s["status"] == "skipped" else "FAIL")
            print(f"{s['name']:<22} {icon:<10} {s['duration']:>8.1f}s")
        print("-" * 60)
        print(f"{'TOTAL':<22} {overall_status.upper():<10} {total_runtime:>8.1f}s")
        print("=" * 60)

    except Exception as e:
        print(f"\n[FATAL] run_pipeline.py hit an unexpected error: {e}")
    finally:
        sys.stdout = real_stdout
        log_f.close()


if __name__ == "__main__":
    main()
