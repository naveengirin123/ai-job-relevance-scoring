"""
naukri_agent.py — Main orchestrator for the Naukri Job Application Bot.

Page structure confirmed from DevTools screenshots:
  - URL:  https://www.naukri.com/mnjuser/recommendedjobs
  - Tabs: div.tab-wrapper#{id}  >  div.tab-list-item
      id="profile"        → Profile (50)
      id="apply"          → Applies (59)
      id="top_candidate"  → Top Candidate (76)
      id="preference"     → Preferences (59)
      id="similar_jobs"   → You might like (45)
  - Clicking a job card opens a RIGHT PANEL (same page, no new tab)
  - Apply button confirmed: button#apply-button
  - Chatbot confirmed:      #_lvgdu2szChatbotContainer
  - Applied confirmation:   div.job-title-text  ("Applied to ...")
"""
import asyncio
import logging
import os
import random
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext

from section_parser import SectionParser
from job_processor import JobProcessor
from report_generator import ReportGenerator

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "naukri_agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("NaukriAgent")

# ── Config ────────────────────────────────────────────────────────────────────
RECOMMENDED_URL = "https://www.naukri.com/mnjuser/recommendedjobs"
LOGIN_URL       = "https://www.naukri.com/nlogin/login"
MAX_APPLIES     = int(os.getenv("MAX_APPLIES_PER_RUN", "25"))

# Confirmed tab wrapper IDs from DevTools (screenshots 3-6)
TABS = [
    {"id": "profile",       "label": "Profile"},
    {"id": "apply",         "label": "Applies"},
    {"id": "top_candidate", "label": "Top Candidate"},
    {"id": "preference",    "label": "Preferences"},
    {"id": "similar_jobs",  "label": "You might like"},
]


class NaukriAgent:
    def __init__(self):
        self.applied_jobs: list[dict]            = []
        self.applied_ids:  set[str]              = set()
        self.skipped:      int                   = 0
        self.errors:       int                   = 0
        self.apply_count:  int                   = 0
        self.page:         Page | None           = None
        self.context:      BrowserContext | None = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _human_delay(self, lo: float = 1.5, hi: float = 4.0) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    async def _scroll_down(self, times: int = 3) -> None:
        for _ in range(times):
            await self.page.mouse.wheel(0, random.randint(300, 500))
            await asyncio.sleep(random.uniform(0.5, 1.0))

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self) -> bool:
        email    = os.getenv("NAUKRI_EMAIL", "")
        password = os.getenv("NAUKRI_PASSWORD", "")
        if not email or not password:
            logger.error("NAUKRI_EMAIL / NAUKRI_PASSWORD not set in .env")
            return False

        logger.info("Navigating to login page …")
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self._human_delay(2, 4)

        try:
            try:
                await self.page.click("button#cookieConsent", timeout=3000)
            except Exception:
                pass

            email_sel = (
                "input[type='text'][placeholder*='Email'],"
                "input#usernameField,"
                "input[name='username']"
            )
            await self.page.wait_for_selector(email_sel, timeout=15000)
            await self.page.fill(email_sel, "")
            await self._human_delay(0.4, 0.8)
            for ch in email:
                await self.page.type(email_sel, ch, delay=random.randint(40, 100))

            await self.page.fill("input[type='password']", "")
            await self._human_delay(0.3, 0.7)
            for ch in password:
                await self.page.type("input[type='password']", ch,
                                     delay=random.randint(40, 100))

            await self._human_delay(1, 2)
            await self.page.click("button[type='submit']")
            await self.page.wait_for_url("**/mnjuser/**", timeout=20000)
            logger.info("Login successful ✓")
            return True

        except Exception as exc:
            logger.error(f"Login failed: {exc}")
            try:
                await self.page.screenshot(path="logs/login_fail.png")
            except Exception:
                pass
            return False

    # ── Tab navigation ─────────────────────────────────────────────────────────

    async def _click_tab(self, tab_id: str, tab_label: str) -> bool:
        """
        Click a tab using its confirmed div.tab-wrapper#{id} selector.
        Falls back to text-based selectors if needed.
        """
        # Primary: confirmed from screenshots — div.tab-wrapper#{id} > div.tab-list-item
        primary_sels = [
            f"div.tab-wrapper#{tab_id} div.tab-list-item",
            f"div[id='{tab_id}'] div.tab-list-item",
            f"#tab-wrapper-{tab_id} div.tab-list-item",
        ]
        for sel in primary_sels:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.click()
                    await self._human_delay(1.5, 2.5)
                    logger.info(f"  Clicked tab '{tab_label}' via {sel} ✓")
                    return True
            except Exception:
                pass

        # Fallback: text-based click
        text_sels = [
            f"div.tab-list-item:has-text('{tab_label}')",
            f"[class*='tab']:has-text('{tab_label}')",
            f"li:has-text('{tab_label}')",
            f"button:has-text('{tab_label}')",
            f"a:has-text('{tab_label}')",
        ]
        for sel in text_sels:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.click()
                    await self._human_delay(1.5, 2.5)
                    logger.info(f"  Clicked tab '{tab_label}' via text fallback ✓")
                    return True
            except Exception:
                pass

        logger.warning(f"  Could not find tab: '{tab_label}' (id={tab_id})")
        return False

    # ── Main run ──────────────────────────────────────────────────────────────

    async def run(self) -> dict:
        logger.info("=" * 60)
        logger.info(f"Run started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Max applies  : {MAX_APPLIES}")
        logger.info("=" * 60)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            )
            self.context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await self.context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self.page = await self.context.new_page()

            # ── Login ──────────────────────────────────────────────────────────
            if not await self.login():
                await browser.close()
                return self._summary()

            # ── Recommended jobs page ──────────────────────────────────────────
            logger.info("Loading recommended jobs page …")
            await self.page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")

            # Wait for tabs
            try:
                await self.page.wait_for_selector(
                    "div.tab-wrapper, div.tab-list-item, [class*='tab-list']",
                    timeout=15000
                )
                logger.info("Tabs loaded ✓")
            except Exception:
                logger.warning("Tabs not detected — proceeding anyway")

            await self._human_delay(2, 3)

            parser    = SectionParser(self.page)
            processor = JobProcessor(
                self.page, self.context,
                self.applied_ids, self.applied_jobs,
            )

            # ── Process each tab ───────────────────────────────────────────────
            for tab in TABS:
                if self.apply_count >= MAX_APPLIES:
                    logger.info(f"Reached max applies ({MAX_APPLIES}) — stopping.")
                    break

                logger.info(f"\n{'═'*50}")
                logger.info(f"  TAB: {tab['label']}  (id={tab['id']})")
                logger.info(f"{'═'*50}")

                clicked = await self._click_tab(tab["id"], tab["label"])
                if not clicked:
                    logger.info(f"  Could not click tab '{tab['label']}' — skipping")
                    continue

                await self._human_delay(2, 3)
                await self._scroll_down(2)
                await self._human_delay(1, 2)

                job_cards = await parser.get_all_jobs_on_tab()
                if not job_cards:
                    logger.info(f"  No job cards found in '{tab['label']}'")
                    continue

                logger.info(f"  Found {len(job_cards)} jobs in '{tab['label']}'")

                for idx, card_info in enumerate(job_cards):
                    if self.apply_count >= MAX_APPLIES:
                        break

                    result = await processor.process_job(card_info, tab["label"], idx)
                    if   result == "applied": self.apply_count += 1
                    elif result == "skipped": self.skipped     += 1
                    elif result == "error":   self.errors      += 1

                    await self._human_delay(2, 4)

            await browser.close()

        summary = self._summary()
        logger.info("\n" + "=" * 60)
        logger.info("RUN COMPLETE")
        logger.info(f"  Applied : {summary['jobs_applied']}")
        logger.info(f"  Skipped : {summary['jobs_skipped']}")
        logger.info(f"  Errors  : {summary['errors']}")
        logger.info(f"  Scanned : {summary['jobs_scanned']}")
        logger.info("=" * 60)
        return summary

    def _summary(self) -> dict:
        return {
            "jobs_scanned": self.apply_count + self.skipped + self.errors,
            "jobs_applied": self.apply_count,
            "jobs_skipped": self.skipped,
            "errors":       self.errors,
            "applied_list": self.applied_jobs,
        }


async def main():
    agent    = NaukriAgent()
    summary  = await agent.run()
    reporter = ReportGenerator()
    reporter.save_session_data(summary["applied_list"])
    if datetime.now().hour >= 23:
        reporter.generate_daily_report()


if __name__ == "__main__":
    asyncio.run(main())