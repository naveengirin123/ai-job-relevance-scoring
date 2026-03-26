"""
section_parser.py — Gets all job cards visible in the current tab.

Confirmed selectors from DevTools screenshots:
  - Job cards:  article.jobTuple  (data-job-id attribute confirmed)
  - Title:      p.title.ellipsis  OR  a.title
  - Company:    a.subTitle  /  .companyInfo .subheading
  - Location:   li.location span  (or similar)
  - Skills:     ul.tags li  (dot-separated at bottom)
  - Tab items:  div.tab-wrapper#{id}  >  div.tab-list-item
"""
import logging
import re
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger("SectionParser")

# ── Card-level selectors ───────────────────────────────────────────────────────
CARD_SELS = [
    "article.jobTuple",
    "article[data-job-id]",
    "[data-job-id]",
    ".jobTuple",
    ".job-container",
    ".jc__card",
]

TITLE_SELS = (
    "p.title.ellipsis,"
    "a.title,"
    "p[class*='title'],"
    "a[class*='title'],"
    "[class*='ellipsis'] a"
)

COMP_SELS = (
    "a.subTitle,"
    ".subheading a,"
    "[class*='companyInfo'] a,"
    "[class*='subTitle'],"
    ".comp-name"
)

LOC_SELS = (
    "li.location span,"
    "li[class*='location'] span,"
    "[class*='locWdth'],"
    "[class*='location']"
)

SKILL_SELS = (
    "ul.tags li,"
    ".keyskill,"
    "[class*='tag'],"
    "[class*='skill']"
)


class SectionParser:
    def __init__(self, page: Page):
        self.page = page

    async def get_all_jobs_on_tab(self) -> list[dict[str, Any]]:
        """Return all visible job cards on the currently active tab."""
        for sel in CARD_SELS:
            els = await self.page.query_selector_all(sel)
            if els:
                logger.info(f"  Selector '{sel}' → {len(els)} cards found")
                cards = []
                for el in els:
                    info = await self._card_info(el)
                    if info:
                        cards.append(info)
                if cards:
                    return cards

        # Fallback: collect title links directly
        return await self._link_fallback()

    # ── Link fallback ──────────────────────────────────────────────────────────
    async def _link_fallback(self) -> list[dict]:
        links = await self.page.query_selector_all(TITLE_SELS)
        cards, seen = [], set()
        for lnk in links:
            href  = await lnk.get_attribute("href") or ""
            title = (await lnk.text_content() or "").strip()
            if not title or href in seen:
                continue
            seen.add(href)
            cards.append({
                "element":  lnk,
                "job_id":   self._id_from_url(href) or f"fb_{hash(href)}",
                "title":    title,
                "company":  "",
                "location": "",
                "skills":   [],
                "href":     href,
            })
        logger.info(f"  Link fallback → {len(cards)} cards")
        return cards

    # ── Card info extractor ────────────────────────────────────────────────────
    async def _card_info(self, el) -> dict | None:
        try:
            # job_id from data attribute (confirmed in screenshot: data-job-id="170326030775")
            job_id = (
                await el.get_attribute("data-job-id")
                or await el.get_attribute("id")
                or ""
            )

            # Title + href — try <p> first (confirmed: p.title.ellipsis), then <a>
            title = ""
            href  = ""
            for t_sel in [
                "p.title.ellipsis",
                "a.title",
                "p[class*='title']",
                "a[class*='title']",
            ]:
                t_el = await el.query_selector(t_sel)
                if t_el:
                    title = (await t_el.text_content() or "").strip()
                    # If it's a <p>, find the parent <a> for the href
                    try:
                        parent_a = await t_el.query_selector("xpath=ancestor::a[1]")
                        if not parent_a:
                            parent_a = await el.query_selector("a.title, a[href*='job-listings'], a[href*='naukri.com']")
                        if parent_a:
                            href = await parent_a.get_attribute("href") or ""
                    except Exception:
                        href = await t_el.get_attribute("href") or ""
                    if title:
                        break

            if not title:
                return None

            if not job_id:
                job_id = self._id_from_url(href)

            # Company
            company = ""
            for c_sel in ["a.subTitle", ".subheading a", "[class*='companyInfo'] a", "[class*='subTitle']"]:
                c_el = await el.query_selector(c_sel)
                if c_el:
                    company = (await c_el.text_content() or "").strip()
                    if company:
                        break

            # Location
            location = ""
            for l_sel in ["li.location span", "li[class*='location'] span", "[class*='location']"]:
                l_el = await el.query_selector(l_sel)
                if l_el:
                    location = (await l_el.text_content() or "").strip()
                    if location:
                        break

            # Skills (ul.tags li confirmed from screenshot)
            skills = []
            for s_sel in ["ul.tags li", ".keyskill", "[class*='tag']"]:
                s_els = await el.query_selector_all(s_sel)
                if s_els:
                    for s in s_els:
                        txt = (await s.text_content() or "").strip()
                        # Filter out stray punctuation like "•"
                        if txt and txt not in ("•", "·", "|", "-"):
                            skills.append(txt)
                    if skills:
                        break

            # Experience (e.g. "6-10 Yrs")
            experience = ""
            for e_sel in ["li.experience", "li[class*='exp']", "[class*='experience']"]:
                e_el = await el.query_selector(e_sel)
                if e_el:
                    experience = (await e_el.text_content() or "").strip()
                    if experience:
                        break

            return {
                "element":    el,
                "job_id":     job_id or f"u_{hash(title + company)}",
                "title":      title,
                "company":    company,
                "location":   location,
                "skills":     skills,
                "experience": experience,
                "href":       href,
            }

        except Exception as exc:
            logger.debug(f"Card info error: {exc}")
            return None

    @staticmethod
    def _id_from_url(url: str) -> str:
        m = re.search(r"-(\d{6,12})(?:\?|$|&|/)", url)
        return m.group(1) if m else ""