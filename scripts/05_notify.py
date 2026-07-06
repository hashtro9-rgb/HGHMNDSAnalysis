"""05_notify.py - email a summary report when the pipeline finishes.

Uses Gmail SMTP via smtplib. Credentials come from environment variables:
  GMAIL_USER            the sending Gmail address
  GMAIL_APP_PASSWORD    a 16-character Gmail "App Password" (NOT your normal
                         Gmail password -- Google blocks plain-password SMTP
                         logins for security).
  NOTIFY_EMAIL          (optional) recipient address; falls back to
                         config/settings.py NOTIFY_EMAIL if unset.

How to get a Gmail App Password:
  1. Turn on 2-Step Verification on the sending Gmail account:
     https://myaccount.google.com/security
  2. Go to https://myaccount.google.com/apppasswords
  3. Create an app password (name it e.g. "HGHMNDS Pipeline"), copy the
     16-character code Google shows you.
  4. Set it as the GMAIL_APP_PASSWORD secret/env var -- never commit it.

If sending fails for any reason (missing creds, SMTP error, no network),
the report is written to logs/report_[timestamp].txt and printed to the
console instead. The pipeline still counts as complete either way -- this
script never raises past its own boundary.
"""
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

ASSETS_DIR = ROOT / settings.ASSETS_DIR
LOGS_DIR = ROOT / settings.LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)
STATUS_FILE = LOGS_DIR / "pipeline_status.json"
DASHBOARD_URL = "https://hashtro9-rgb.github.io/HGHMNDSAnalysis/"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def build_report():
    status = load_json(STATUS_FILE, {})
    summary = load_json(ASSETS_DIR / "summary.json", {})
    diff = load_json(ASSETS_DIR / "weekly_diff.json", {})

    overall_ok = status.get("overall_status", "success") != "failure"
    run_date = status.get("run_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    runtime = status.get("runtime_seconds")
    runtime_str = f"{runtime:.1f}s" if isinstance(runtime, (int, float)) else "N/A"

    new_products = diff.get("new_products", [])
    removed_products = diff.get("disappeared_products", [])
    price_changes = diff.get("price_changes", [])
    price_up = [p for p in price_changes if p.get("pct_change", 0) > 0]
    price_down = [p for p in price_changes if p.get("pct_change", 0) < 0]
    avg_up = (sum(p["pct_change"] for p in price_up) / len(price_up)) if price_up else 0
    avg_down = (sum(abs(p["pct_change"]) for p in price_down) / len(price_down)) if price_down else 0

    try:
        products = pd.read_json(ASSETS_DIR / "products.json")
        top5 = (products.sort_values("sold_final", ascending=False).head(5)
                [["platform", "product_name_clean", "sold_final"]].to_dict("records"))
    except Exception:
        top5 = []

    steps = status.get("steps", [])

    lines = []
    lines.append(f"Run date       : {run_date}")
    lines.append(f"Runtime        : {runtime_str}")
    lines.append("")
    lines.append(f"New products found     : {len(new_products)}")
    for p in new_products[:10]:
        lines.append(f"    + {p.get('platform','')}: {p.get('product_name','')}")
    lines.append(f"Removed products       : {len(removed_products)}")
    for p in removed_products[:10]:
        lines.append(f"    - {p.get('platform','')}: {p.get('product_name','')}")
    lines.append(f"Price changes (>20%)   : {len(price_up)} up (avg +{avg_up:.1f}%), "
                 f"{len(price_down)} down (avg -{avg_down:.1f}%)")
    lines.append("")
    lines.append("Current snapshot:")
    lines.append(f"    Shopee  : {summary.get('shopee_count', 'N/A')} products, "
                 f"avg {summary.get('avg_price_shopee', 'N/A')} PHP, "
                 f"rating {summary.get('avg_rating_shopee', 'N/A')}")
    lines.append(f"    Lazada  : {summary.get('lazada_count', 'N/A')} products, "
                 f"avg {summary.get('avg_price_lazada', 'N/A')} PHP, "
                 f"rating {summary.get('avg_rating_lazada', 'N/A')}")
    lines.append(f"    Total sold      : {summary.get('total_sold', 'N/A')}")
    lines.append(f"    Total reviews   : {summary.get('total_reviews', 'N/A')}")
    lines.append(f"    Suspicious flagged: {summary.get('suspicious_count', 'N/A')}")
    lines.append("")
    lines.append("Top 5 bestsellers:")
    for i, p in enumerate(top5, 1):
        lines.append(f"    {i}. [{p['platform']}] {p['product_name_clean']} "
                     f"-- {int(p['sold_final'])} sold")
    lines.append("")
    lines.append("Pipeline steps:")
    if steps:
        for s in steps:
            icon = "PASS" if s.get("status") == "success" else (
                "SKIP" if s.get("status") == "skipped" else "FAIL")
            lines.append(f"    [{icon}] {s.get('name','?')} ({s.get('duration', 0):.1f}s)")
    else:
        lines.append("    (no run_pipeline.py status found -- run standalone)")
    lines.append("")
    lines.append(f"Dashboard: {DASHBOARD_URL}")

    subject = (f"✅ HGHMNDS Weekly Report — {datetime.now().strftime('%Y-%m-%d')}"
               if overall_ok else
               f"❌ HGHMNDS Pipeline Failed — {datetime.now().strftime('%Y-%m-%d')}")
    return subject, "\n".join(lines), status.get("log_file")


def send_email(subject, body, log_file):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFY_EMAIL") or settings.NOTIFY_EMAIL

    if not gmail_user or not gmail_pass:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set in environment")

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if log_file and Path(log_file).exists():
        with open(log_file, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={Path(log_file).name}")
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, recipient, msg.as_string())


def save_fallback_report(subject, body):
    path = LOGS_DIR / f"report_{TIMESTAMP}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(subject + "\n" + "=" * len(subject) + "\n\n" + body + "\n")
    return path


def main():
    try:
        subject, body, log_file = build_report()
    except Exception as e:
        subject = f"❌ HGHMNDS Pipeline Failed — {datetime.now().strftime('%Y-%m-%d')}"
        body = f"Failed to build the report itself: {e}"
        log_file = None

    print(subject)
    print("-" * len(subject))
    print(body)

    try:
        send_email(subject, body, log_file)
        print("\n[OK] Email sent successfully.")
    except Exception as e:
        print(f"\n[!] Email send failed ({e}). Saving fallback report instead.")
        path = save_fallback_report(subject, body)
        print(f"[OK] Fallback report saved: {path}")

    # Never fail the pipeline over notification issues.
    print("\n[DONE] Notification step complete.")


if __name__ == "__main__":
    main()
