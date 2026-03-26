"""
report_generator.py — Persists applied jobs to JSON and generates Excel reports.
"""
import json
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("ReportGenerator")

DATA_DIR    = Path("data")
REPORTS_DIR = Path("reports")
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

SESSION_FILE = DATA_DIR / "applied_jobs.json"

COLUMNS = ["Job Title", "Company", "Location", "Skills", "Section", "Score", "Date"]


class ReportGenerator:

    # ── Persist session data ───────────────────────────────────────────────────

    def save_session_data(self, applied_jobs: list[dict]) -> None:
        """Append this session's applied jobs to the persistent JSON store."""
        existing: list[dict] = []
        if SESSION_FILE.exists():
            try:
                existing = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Could not read existing session data: {exc}")

        existing.extend(applied_jobs)

        # Deduplicate by (Job Title + Company + Date)
        seen:   set[str]   = set()
        unique: list[dict] = []
        for job in existing:
            key = (
                f"{job.get('Job Title', '')}|"
                f"{job.get('Company', '')}|"
                f"{job.get('Date', '')}"
            ).lower()
            if key not in seen:
                seen.add(key)
                unique.append(job)

        SESSION_FILE.write_text(
            json.dumps(unique, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Session data saved — total records in store: {len(unique)}")

    # ── Daily report ───────────────────────────────────────────────────────────

    def generate_daily_report(self, target_date: str | None = None) -> Path:
        """
        Generate an Excel report for target_date (YYYY-MM-DD).
        Defaults to today's date.
        """
        target = target_date or date.today().isoformat()
        logger.info(f"Generating daily report for {target} …")

        all_jobs = self._load_all_jobs()
        today_jobs = [j for j in all_jobs if j.get("Date", "") == target]

        df = pd.DataFrame(today_jobs, columns=COLUMNS)

        filename = REPORTS_DIR / f"naukri_daily_report_{target}.xlsx"

        with pd.ExcelWriter(str(filename), engine="openpyxl") as writer:
            # Main sheet
            df.to_excel(writer, index=False, sheet_name="Applied Jobs")
            self._autofit_columns(writer, "Applied Jobs")

            # Summary sheet
            summary_df = pd.DataFrame({
                "Metric": [
                    "Report Date",
                    "Total Jobs Applied",
                    "Unique Companies",
                    "Sections Covered",
                    "Generated At",
                ],
                "Value": [
                    target,
                    len(df),
                    df["Company"].nunique() if not df.empty else 0,
                    df["Section"].nunique() if not df.empty else 0,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ],
            })
            summary_df.to_excel(writer, index=False, sheet_name="Summary")
            self._autofit_columns(writer, "Summary")

        logger.info(f"Daily report saved → {filename}")
        return filename

    # ── Range report ───────────────────────────────────────────────────────────

    def generate_range_report(self, start: str, end: str) -> Path:
        """Generate an Excel report covering start … end (inclusive, YYYY-MM-DD)."""
        all_jobs = self._load_all_jobs()
        filtered = [j for j in all_jobs if start <= j.get("Date", "") <= end]

        df       = pd.DataFrame(filtered, columns=COLUMNS)
        filename = REPORTS_DIR / f"naukri_report_{start}_to_{end}.xlsx"
        df.to_excel(str(filename), index=False)
        logger.info(f"Range report saved → {filename}")
        return filename

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _load_all_jobs(self) -> list[dict]:
        if not SESSION_FILE.exists():
            return []
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(f"Failed to load session data: {exc}")
            return []

    @staticmethod
    def _autofit_columns(writer, sheet_name: str) -> None:
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(
                (len(str(cell.value or "")) for cell in col),
                default=10,
            )
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
