"""
debug_page.py — Logs into Naukri, goes to recommended jobs page,
and prints all headings + class names so we can find correct selectors.

Run:
  .venv/bin/python debug_page.py
"""
import asyncio
import os
import random
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

LOGIN_URL       = "https://www.naukri.com/nlogin/login"
RECOMMENDED_URL = "https://www.naukri.com/mnjuser/recommendedjobs"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()

        # ── Login ──────────────────────────────────────────────────────────────
        print("Logging in …")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        email    = os.getenv("NAUKRI_EMAIL", "")
        password = os.getenv("NAUKRI_PASSWORD", "")

        email_sel = (
            "input[type='text'][placeholder*='Email'],"
            "input#usernameField,"
            "input[name='username']"
        )
        await page.wait_for_selector(email_sel, timeout=15000)
        await page.fill(email_sel, "")
        for ch in email:
            await page.type(email_sel, ch, delay=random.randint(40, 100))

        await page.fill("input[type='password']", "")
        for ch in password:
            await page.type("input[type='password']", ch, delay=random.randint(40, 100))

        await asyncio.sleep(1)
        await page.click("button[type='submit']")
        await page.wait_for_url("**/mnjuser/**", timeout=20000)
        print("Login successful ✓")

        # ── Go to recommended jobs ─────────────────────────────────────────────
        await page.goto(RECOMMENDED_URL, wait_until="domcontentloaded")
        await asyncio.sleep(5)  # let JS render

        # ── Scroll to load all sections ────────────────────────────────────────
        for _ in range(6):
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(1)

        # ── Save full HTML for inspection ──────────────────────────────────────
        html = await page.content()
        Path("debug_page.html").write_text(html, encoding="utf-8")
        print("Full HTML saved to debug_page.html")

        # ── Print all heading texts ────────────────────────────────────────────
        print("\n── All headings (h1/h2/h3/h4) ──────────────────────────")
        for tag in ["h1", "h2", "h3", "h4"]:
            els = await page.query_selector_all(tag)
            for el in els:
                text = (await el.text_content() or "").strip()
                if text:
                    print(f"  <{tag}> : {text!r}")

        # ── Print elements whose class contains common section keywords ────────
        print("\n── Elements with 'section','widget','title','heading' in class ──")
        els = await page.query_selector_all(
            "[class*='section'],[class*='widget'],[class*='title'],[class*='heading']"
        )
        seen = set()
        for el in els:
            cls  = await el.get_attribute("class") or ""
            text = (await el.text_content() or "").strip()[:80]
            key  = cls[:60]
            if key not in seen and text:
                seen.add(key)
                print(f"  class={cls[:60]!r}  text={text!r}")

        # ── Print all unique class names on the page ───────────────────────────
        print("\n── All unique top-level div/section class names ─────────────")
        divs = await page.query_selector_all("div[class], section[class]")
        classes = set()
        for d in divs:
            cls = await d.get_attribute("class") or ""
            if cls:
                classes.add(cls[:80])
        for c in sorted(classes)[:80]:   # print first 80
            print(f"  {c!r}")

        await browser.close()
        print("\nDone. Check the output above and debug_page.html")


if __name__ == "__main__":
    asyncio.run(main())
