"""
question_engine.py — Answers recruiter chatbot questions.

Two modes:
  1. Heuristic (fast, no API) — pattern-match known question types
  2. Claude API fallback — for unknown questions

Confirmed question types from screenshots:
  "How many years of experience do you have in Power BI?"  → 6
  "How many years of experience do you have in SQL?"       → 6
  "How many years of experience do you have in Python?"    → 2.5
  "How many years of experience do you have in AI?"        → 1.5
  "What is your notice period or last working date?"       → 30th March
  "Are you currently residing in X or willing to relocate?"→ (radio Yes)
  "Fine for 3rd party payroll?"                            → (radio Yes)
  "Previously Employed by Cognizant?"                      → (radio No)
  "do you have experience with Manufacturing domain?"       → -
"""
import asyncio
import logging
import os
import re

import httpx

logger = logging.getLogger("QuestionEngine")

# ── Skill → years map (Naveen's actual experience) ────────────────────────────
SKILL_EXP_MAP: dict[str, float] = {
    "power bi":              6.0,
    "powerbi":               6.0,
    "power query":           6.0,
    "dax":                   6.0,
    "bi tools":              6.0,
    "business intelligence": 6.0,
    "dashboard":             6.0,
    "sql":                   6.0,
    "mysql":                 5.0,
    "postgresql":            4.0,
    "oracle":                3.0,
    "python":                2.5,
    "alteryx":               4.5,
    "tableau":               3.0,
    "excel":                 6.0,
    "vba":                   3.0,
    "analytics":             6.0,
    "data analytics":        6.0,
    "data analysis":         6.0,
    "reporting":             6.0,
    "mis":                   5.0,
    "sap":                   4.0,
    "etl":                   4.0,
    "machine learning":      1.5,
    "ml":                    1.5,
    "ai":                    1.5,
    "artificial intelligence": 1.5,
    "azure":                 2.0,
    "aws":                   1.5,
    "gcp":                   1.0,
    "looker":                1.5,
    "qlik":                  1.5,
    "data warehouse":        3.0,
    "dwh":                   3.0,
    "snowflake":             1.5,
    "r":                     1.5,
    "spark":                 1.0,
}

TOTAL_EXP        = float(os.getenv("TOTAL_EXPERIENCE",  "6"))
CURRENT_CTC      = float(os.getenv("CURRENT_CTC",       "10.5"))
EXPECTED_CTC     = float(os.getenv("EXPECTED_CTC",      "15.0"))
NOTICE_PERIOD    = os.getenv("NOTICE_PERIOD",    "30 days")
LAST_WORKING_DAY = os.getenv("LAST_WORKING_DAY", "30th April 2026")

# Previous companies — used for "Previously employed by X?" questions
PREVIOUS_COMPANIES = ["concentrix", "randstad"]
CURRENT_COMPANY    = "techmaxim"

CLAUDE_SYSTEM = f"""You are filling a job application form for {os.getenv('CANDIDATE_NAME', 'Naveen Giri')}.

Candidate profile:
- Name: Naveen Giri, Sr. Data Analyst, 6 years experience
- Skills: Power BI, SQL, Python, Tableau, Alteryx, Excel, DAX, Data Visualization, ETL, SAP, MIS
- Current company: TechMaxIT
- Previous companies: Concentrix, Randstad India
- Notice period: 30 days
- Current CTC: ~10.5 LPA, Expected: ~15 LPA
- Location: Delhi, India. Willing to relocate.
- Education: MBA (Amity University), B.Com (Delhi University)
- Indian citizen

Rules:
- For yes/no questions return ONLY "Yes" or "No"
- For multiple choice return ONLY the exact option text
- For numeric/experience questions return ONLY the number (e.g. "6" or "2.5")
- For notice period return "30 days"
- Answer honestly — do NOT claim skills/experience not in profile
- For "Previously employed by X?" — check previous companies list (Concentrix, Randstad)"""


class QuestionEngine:

    def __init__(self):
        self.api_key    = os.getenv("ANTHROPIC_API_KEY", "")
        self.use_claude = bool(self.api_key)

    # ── Sync wrapper ───────────────────────────────────────────────────────────

    def answer(self, question: str, options: list[str] | None = None) -> str:
        """Synchronous answer — tries heuristic first, then Claude API."""
        heuristic = self._heuristic_answer(question, options)
        if heuristic != "-":
            return heuristic
        if self.use_claude:
            try:
                return asyncio.run(self._claude_answer(question, options))
            except Exception as exc:
                logger.warning(f"Claude Q&A error: {exc}")
        return "-"

    async def answer_async(
        self, question: str, options: list[str] | None = None
    ) -> str:
        """Async version."""
        heuristic = self._heuristic_answer(question, options)
        if heuristic != "-":
            return heuristic
        if self.use_claude:
            try:
                return await self._claude_answer(question, options)
            except Exception as exc:
                logger.warning(f"Claude Q&A error: {exc}")
        return "-"

    # ── Heuristic engine ───────────────────────────────────────────────────────

    def _heuristic_answer(self, question: str, options: list[str] | None) -> str:
        if not question:
            return "-"
        q = question.lower().strip()

        # ── CTC ───────────────────────────────────────────────────────────────
        if re.search(r"current\s*(ctc|salary|package|compensation|lpa)", q):
            return self._fmt(CURRENT_CTC)
        if re.search(r"expected\s*(ctc|salary|package|compensation|lpa)", q):
            return self._fmt(EXPECTED_CTC)

        # ── Total experience ──────────────────────────────────────────────────
        if self._is_total_exp(q):
            return self._fmt(TOTAL_EXP)

        # ── Notice period ─────────────────────────────────────────────────────
        if re.search(r"notice\s*period|last\s*working\s*(date|day)", q):
            return NOTICE_PERIOD

        # ── Previously employed by [company]? ─────────────────────────────────
        prev_match = re.search(r"previously\s+employed\s+by\s+(.+?)[\?\.]?$", q)
        if prev_match:
            company = prev_match.group(1).strip().lower()
            if any(prev in company for prev in PREVIOUS_COMPANIES):
                return self._pick_option(options, "yes") or "Yes"
            return self._pick_option(options, "no") or "No"

        # ── "Do you have experience with X?" ─────────────────────────────────
        if re.search(r"do you (have )?(experience|exp) with", q):
            matched = self._match_skills(q)
            return ("yes" if matched else "-")

        # ── Years of experience with skill ────────────────────────────────────
        if re.search(r"(how many )?years?\s*(of)?\s*(experience|exp)", q):
            matched = self._match_skills(q)
            if matched:
                if len(matched) == 1:
                    return self._fmt(matched[0][1])
                if re.search(r"\band\b|\bor\b|/|combined|total", q):
                    return self._fmt(TOTAL_EXP)
                return self._fmt(max(matched, key=lambda x: x[1])[1])
            return self._fmt(TOTAL_EXP)

        # ── Relocation / location ─────────────────────────────────────────────
        if re.search(r"relocat|residing|willing to (move|work)", q):
            return self._pick_option(options, "yes") or "Yes"

        # ── Payroll / 3rd party / contract ───────────────────────────────────
        if re.search(r"payroll|3rd party|third.party|contract|c2h", q):
            return self._pick_option(options, "yes") or "Yes"

        # ── Generic yes/no ────────────────────────────────────────────────────
        if re.search(r"^(are you|do you|will you|can you|is your)\b", q):
            return self._pick_option(options, "yes") or "Yes"

        # ── Skill mention without experience keyword → numeric ────────────────
        matched = self._match_skills(q)
        if matched:
            return self._fmt(matched[0][1])

        return "-"

    # ── Claude fallback ────────────────────────────────────────────────────────

    async def _claude_answer(
        self, question: str, options: list[str] | None
    ) -> str:
        prompt = f"Question: {question}\n"
        if options:
            prompt += f"Options: {options}\nReturn ONLY the exact option text."
        else:
            prompt += "Return ONLY the answer value, nothing else."

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type":      "application/json",
                },
                json={
                    "model":      "claude-haiku-4-5-20251001",
                    "max_tokens": 80,
                    "system":     CLAUDE_SYSTEM,
                    "messages":   [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _match_skills(self, q: str) -> list[tuple[str, float]]:
        found  = []
        q_work = q
        for skill, years in sorted(SKILL_EXP_MAP.items(), key=lambda x: -len(x[0])):
            if skill in q_work:
                found.append((skill, years))
                q_work = q_work.replace(skill, " ", 1)
        return found

    @staticmethod
    def _is_total_exp(q: str) -> bool:
        return bool(
            re.search(r"total\s+(years?\s+of\s+)?(work\s+)?(exp|experience)", q)
            or re.search(r"(overall|total)\s+(professional\s+)?(exp|experience)", q)
            or q.strip() in (
                "experience", "years of experience", "total experience",
                "work experience", "total work experience",
            )
        )

    @staticmethod
    def _pick_option(options: list[str] | None, prefer: str) -> str:
        """Return the option whose text contains `prefer` (case-insensitive)."""
        if not options:
            return ""
        for opt in options:
            if prefer.lower() in opt.lower():
                return opt
        return options[0]

    @staticmethod
    def _fmt(val: float) -> str:
        return str(int(val)) if val == int(val) else f"{val:.1f}"