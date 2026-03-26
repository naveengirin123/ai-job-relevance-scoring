import logging
import asyncio
from scoring_engine import ScoringEngine, MIN_SCORE

logger = logging.getLogger("JobProcessor")


class JobProcessor:

    def __init__(self):

        self.scorer = ScoringEngine()

        self.applied = 0


    async def process_job(

        self,
        page,
        job,
        index,
        max_applies

    ):

        if self.applied >= max_applies:

            logger.info("Max applies reached")
            return


        # SCORE JOB
        result = await self.scorer.score_job(

            title=job["title"],
            skills=job["skills"]

        )

        score = result["total_score"]

        logger.info(f"[{index}] {job['title']} | score {score}")


        # BELOW THRESHOLD
        if score < MIN_SCORE:

            logger.info("Below threshold")

            return


        logger.info("Above threshold ✓")


        # OPEN JOB CARD
        try:

            await job["element"].click()

            await asyncio.sleep(2)

        except Exception as e:

            logger.info("Could not open job")

            return


        # APPLY
        success = await self.apply(page)

        if success:

            self.applied += 1

            logger.info(f"Applied ✓ total={self.applied}")

        else:

            logger.info("Apply failed")


    async def apply(self,page):

        logger.info("Searching Apply button")


        selectors = [

            "button:has-text('Apply')",

            "button:has-text('Easy Apply')",

            "a:has-text('Apply')",

            ".apply-button"

        ]


        apply_btn = None


        for selector in selectors:

            try:

                apply_btn = await page.query_selector(selector)

                if apply_btn:

                    break

            except:

                pass


        if not apply_btn:

            logger.info("Apply button not found")

            return False


        try:

            await apply_btn.click()

            logger.info("Clicked Apply ✓")

            await asyncio.sleep(3)

        except:

            logger.info("Apply click failed")

            return False


        # SUBMIT BUTTON
        submit_selectors = [

            "button:has-text('Submit')",

            "button:has-text('Continue')",

            "button:has-text('Next')"

        ]


        for selector in submit_selectors:

            try:

                btn = await page.query_selector(selector)

                if btn:

                    await btn.click()

                    logger.info("Submitted ✓")

                    await asyncio.sleep(2)

                    return True

            except:

                pass


        logger.info("No submit step")

        return True