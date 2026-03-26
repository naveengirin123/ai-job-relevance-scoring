"""
scheduler.py — Runs the Naukri bot on a fixed schedule.

Times:
  09:00 — Full apply run
  14:00 — Full apply run
  18:00 — Full apply run
  23:00 — Daily Excel report (no applications)

Usage:
  python scheduler.py
"""
import asyncio
import logging
import time
from datetime import datetime

import schedule

from naukri_agent import NaukriAgent
from report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("Scheduler")


def run_agent():
    logger.info(f"⏰  Scheduled apply run — {datetime.now().strftime('%H:%M')}")
    agent    = NaukriAgent()
    reporter = ReportGenerator()
    summary  = asyncio.run(agent.run())
    reporter.save_session_data(summary["applied_list"])
    logger.info(
        f"    Applied: {summary['jobs_applied']}  "
        f"Skipped: {summary['jobs_skipped']}  "
        f"Errors: {summary['errors']}"
    )


def run_report():
    logger.info("📊  Generating daily report …")
    reporter = ReportGenerator()
    path     = reporter.generate_daily_report()
    logger.info(f"    Saved → {path}")


def main():
    schedule.every().day.at("09:00").do(run_agent)
    schedule.every().day.at("14:00").do(run_agent)
    schedule.every().day.at("18:00").do(run_agent)
    schedule.every().day.at("23:00").do(run_report)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    logger.info("Apply runs : 09:00 | 14:00 | 18:00")
    logger.info("Report run : 23:00")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
