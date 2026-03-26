"""
form_engine.py — Handles Naukri's chatbot-style application popup.

Confirmed from DevTools screenshots:
  Chatbot container:  #_lvgdu2szChatbotContainer  (div.chatbot_Drawer.chatbot_right)
  Message container:  #_lvgdu2szMessages  (div.chatbot_MessageContainer)
  Messages list:      ul#chatList__lvgdu2szMessages  (ul.list)
  Bot messages:       li.botItem  >  div.botMsg.msg  >  div  >  span
  Radio options:      #singleselect_radiobutton__lvgdu2szMessages  label
  Text input:         form inside #sendMsgbtn_container__lvgdu2szInputBox
  Send button:        button inside that form
  Save button:        button.styles_save-job-button__WLm_s   (bottom of page)
  Chatbot overlay:    div#_lvgdu2sz2.chatbot_Overlay.show
"""
import asyncio
import logging
import random
from typing import Any

from playwright.async_api import Page

from question_engine import QuestionEngine

logger = logging.getLogger("FormEngine")

# ── Confirmed chatbot selectors ────────────────────────────────────────────────
CHATBOT_CONTAINER_SELS = [
    "#_lvgdu2szChatbotContainer",
    "div.chatbot_Drawer",
    "[class*='chatbot_Drawer']",
    "[class*='chatBot']",
    "[class*='chatbot']",
    "div[role='dialog']",
    ".ltBx",
    "[class*='applyContainer']",
]

BOT_MSG_SELS = [
    "li.botItem div.botMsg span",
    "li.botItem .msg span",
    "li.botItem span",
    "[class*='botMsg'] span",
    "[class*='bot-message'] span",
    "[class*='botMessage'] span",
]

RADIO_OPTION_SELS = [
    "#singleselect_radiobutton__lvgdu2szMessages label",
    "[id*='singleselect_radiobutton'] label",
    "[class*='radiobutton'] label",
    "[class*='option'] label",
    "[class*='answer']",
    "[class*='choice']",
    "input[type='radio'] + label",
    "input[type='radio']",
]

TEXT_INPUT_SELS = [
    "#sendMsgbtn_container__lvgdu2szInputBox input[type='text']",
    "#sendMsgbtn_container__lvgdu2szInputBox input",
    "#sendMsgbtn_container__lvgdu2szInputBox textarea",
    "[id*='sendMsgbtn'] input",
    "[id*='InputBox'] input",
    "[class*='sendMsg'] input",
    "form input[type='text']",
    "form textarea",
    "input[type='text']",
    "textarea",
]

SEND_BTN_SELS = [
    "#sendMsgbtn_container__lvgdu2szInputBox button[type='submit']",
    "#sendMsgbtn_container__lvgdu2szInputBox button",
    "[id*='sendMsgbtn'] button",
    "[class*='sendMsg'] button",
    "form button[type='submit']",
    "form button",
    "button:has-text('Send')",
]

SAVE_BTN_SELS = [
    "button.styles_save-job-button__WLm_s",
    "button[class*='save-job-button']",
    "button:has-text('Save')",
    "button:has-text('Submit')",
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "input[type='submit']",
]

SUCCESS_SIGNALS = [
    "successfully applied",
    "application submitted",
    "thank you",
    "you have applied",
    "applied successfully",
    "applied to",
]


class FormEngine:
    def __init__(self, page: Page, q_engine: QuestionEngine):
        self.page     = page
        self.q_engine = q_engine

    # ── Main entry ─────────────────────────────────────────────────────────────

    async def handle_chatbot(self) -> bool:
        """
        Detect chatbot popup and answer all questions.
        Returns True when application is submitted or no chatbot is found.
        """
        chatbot = await self._find_chatbot()
        if not chatbot:
            logger.info("    No chatbot popup found — assuming direct apply ✓")
            return True

        logger.info("    Chatbot popup detected ✓")

        prev_question = ""
        max_rounds    = 25

        for round_num in range(max_rounds):
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # ── Check if done ──────────────────────────────────────────────────
            if await self._is_done():
                logger.info(f"    Chatbot completed after {round_num} rounds ✓")
                return True

            chatbot = await self._find_chatbot()
            if not chatbot:
                logger.info("    Chatbot closed — done ✓")
                return True

            # ── Get latest bot question ────────────────────────────────────────
            question_text = await self._get_latest_question()
            if not question_text or question_text == prev_question:
                # No new question — wait and retry
                await asyncio.sleep(1.2)
                question_text = await self._get_latest_question()
                if not question_text or question_text == prev_question:
                    logger.debug("    No new question, trying Save …")
                    saved = await self._click_save()
                    if saved:
                        await asyncio.sleep(1.5)
                        if await self._is_done():
                            return True
                    continue

            prev_question = question_text
            logger.info(f"    Q{round_num+1}: {question_text[:80]!r}")

            # ── Get radio options (if any) ─────────────────────────────────────
            options = await self._get_radio_options()

            # ── Answer via question engine ─────────────────────────────────────
            answer = await self.q_engine.answer_async(question_text, options or None)
            logger.info(f"    A: {answer!r}")

            # ── Click radio / fill text ────────────────────────────────────────
            answered = False

            if options:
                answered = await self._click_radio(options, answer)

            if not answered:
                answered = await self._fill_text_input(answer)

            if not answered:
                logger.warning(f"    Could not answer: {question_text[:60]!r}")

            # ── Click Save/Send ────────────────────────────────────────────────
            await asyncio.sleep(random.uniform(0.4, 0.8))
            await self._click_save()
            await asyncio.sleep(random.uniform(0.8, 1.5))

        logger.warning("    Max chatbot rounds reached")
        return False

    # ── Chatbot finder ─────────────────────────────────────────────────────────

    async def _find_chatbot(self):
        for sel in CHATBOT_CONTAINER_SELS:
            try:
                el = await self.page.wait_for_selector(
                    sel, timeout=2500, state="visible"
                )
                if el:
                    return el
            except Exception:
                pass
        return None

    async def _is_done(self) -> bool:
        try:
            content = (await self.page.content()).lower()
            if any(sig in content for sig in SUCCESS_SIGNALS):
                return True
        except Exception:
            pass
        # Chatbot overlay hidden = done
        try:
            overlay = await self.page.query_selector("#_lvgdu2sz2, [class*='chatbot_Overlay']")
            if overlay:
                cls = await overlay.get_attribute("class") or ""
                if "show" not in cls:
                    return True
        except Exception:
            pass
        return False

    # ── Question extractor ─────────────────────────────────────────────────────

    async def _get_latest_question(self) -> str:
        """Get text of the most recent bot message."""
        for sel in BOT_MSG_SELS:
            try:
                els = await self.page.query_selector_all(sel)
                if els:
                    # Take the last visible bot message
                    for el in reversed(els):
                        if await el.is_visible():
                            text = (await el.text_content() or "").strip()
                            if len(text) > 5:
                                return text
            except Exception:
                pass

        # Fallback: scan full chatbot text for question marks
        try:
            for csel in CHATBOT_CONTAINER_SELS:
                el = await self.page.query_selector(csel)
                if el:
                    full = (await el.text_content() or "")
                    lines = [l.strip() for l in full.split("\n") if "?" in l and len(l.strip()) > 8]
                    if lines:
                        return lines[-1]
        except Exception:
            pass

        return ""

    # ── Radio options ──────────────────────────────────────────────────────────

    async def _get_radio_options(self) -> list[str]:
        for sel in RADIO_OPTION_SELS:
            try:
                els = await self.page.query_selector_all(sel)
                if els:
                    texts = []
                    for el in els:
                        if await el.is_visible():
                            t = (await el.text_content() or "").strip()
                            if t:
                                texts.append(t)
                    if texts:
                        return texts
            except Exception:
                pass
        return []

    async def _click_radio(self, option_texts: list[str], answer: str) -> bool:
        """Click the radio option that best matches `answer`."""
        ans_l = answer.lower().strip()

        for sel in RADIO_OPTION_SELS:
            try:
                els = await self.page.query_selector_all(sel)
                if not els:
                    continue

                # Exact / partial match
                for el in els:
                    if not await el.is_visible():
                        continue
                    text = (await el.text_content() or "").strip().lower()
                    if ans_l in text or text in ans_l:
                        await el.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await el.click()
                        logger.info(f"    Radio clicked: {text!r} ✓")
                        return True

                # Fallback: click first visible option
                for el in els:
                    if await el.is_visible():
                        await el.click()
                        logger.info("    Radio clicked (fallback: first option) ✓")
                        return True

            except Exception:
                pass

        return False

    # ── Text input ─────────────────────────────────────────────────────────────

    async def _fill_text_input(self, answer: str) -> bool:
        if answer == "-":
            return False

        for sel in TEXT_INPUT_SELS:
            try:
                inp = await self.page.query_selector(sel)
                if not inp:
                    continue
                if not await inp.is_visible() or await inp.is_disabled():
                    continue

                await inp.scroll_into_view_if_needed()
                await inp.triple_click()
                await asyncio.sleep(0.15)
                await inp.fill("")
                for ch in str(answer):
                    await inp.type(ch, delay=random.randint(40, 100))
                await asyncio.sleep(random.uniform(0.2, 0.5))

                # Try clicking Send
                await inp.press("Enter")
                await asyncio.sleep(random.uniform(0.3,0.7))
                await self._click_send()


                logger.info(f"    Text filled: {answer!r} ✓")
                return True

            except Exception:
                pass

        return False

    async def _click_send(self) -> bool:
        for sel in SEND_BTN_SELS:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible() and await btn.is_enabled():
                    await btn.click()
                    return True
            except Exception:
                pass
        return False

    # ── Save button ────────────────────────────────────────────────────────────

    async def _click_save(self) -> bool:
        for sel in SAVE_BTN_SELS:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible() and await btn.is_enabled():
                    await btn.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.3, 0.6))
                    await btn.click()
                    logger.info("    Save/Submit clicked ✓")
                    return True
            except Exception:
                pass
        return False