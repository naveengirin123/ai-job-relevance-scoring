import logging
import os

logger = logging.getLogger("ScoringEngine")

ROLE_KEYWORDS = [

    "data analyst",
    "business analyst",
    "bi analyst",
    "business intelligence",
    "analytics",
    "data scientist",
    "bi developer",
    "reporting analyst",
    "mis analyst",
    "dashboard",
    "data analytics"

]

TECH_KEYWORDS = [

    "power bi",
    "tableau",
    "sql",
    "python",
    "excel",
    "dax",
    "etl",
    "power query",
    "alteryx"

]

GOOD_WORDS = [

    "data",
    "analyst",
    "bi",
    "analytics",
    "reporting",
    "dashboard"

]

NEGATIVE_WORDS = [

    "sales",
    "marketing",
    "support",
    "customer service",
    "bpo",
    "call center"

]

TARGET_SKILLS = [

    "sql",
    "python",
    "power bi",
    "tableau",
    "excel",
    "dax",
    "etl",
    "analytics",
    "reporting",
    "dashboard"

]

MIN_SCORE = int(os.getenv("MIN_SCORE","65"))


class ScoringEngine:

    async def score_job(

        self,
        title: str,
        skills: list[str],
        location: str = "",
        experience: str = ""

    ):

        title_score = self._title_score(title)

        skills_score = self._skills_score(skills)

        total_score = round(

            (title_score * 0.80) +
            (skills_score * 0.20),

            2

        )

        logger.info(f"title score = {title_score}")
        logger.info(f"skills score = {skills_score}")

        return {

            "title_score": title_score,

            "skills_score": skills_score,

            "total_score": total_score

        }


    def _title_score(self,title):

        tl = title.lower()

        score = 0


        # STRONG ROLE MATCH
        for role in ROLE_KEYWORDS:

            if role in tl:

                score += 40


        # GOOD WORD MATCH
        for word in GOOD_WORDS:

            if word in tl:

                score += 10


        # TECH BONUS
        for tech in TECH_KEYWORDS:

            if tech in tl:

                score += 15


        # NEGATIVE FILTER
        for bad in NEGATIVE_WORDS:

            if bad in tl:

                score -= 40


        # SPECIAL BOOSTS
        if "senior" in tl or "sr" in tl:

            score += 10


        if "developer" in tl and "bi" in tl:

            score += 20


        if "business intelligence" in tl:

            score += 25


        if "data" in tl and "analyst" in tl:

            score += 30


        return max(0,min(score,100))


    def _skills_score(self,skills):

        if not skills:

            return 0

        skill_text = " ".join(skills).lower()

        matched = 0

        for skill in TARGET_SKILLS:

            if skill in skill_text:

                matched += 1


        if matched == 0:

            return 10


        score = int((matched/len(TARGET_SKILLS))*100*2)

        return min(score,100)