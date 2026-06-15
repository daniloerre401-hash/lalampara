import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_browser = None
_page = None
_playwright = None


async def kill_browser():
    global _browser, _page, _playwright
    for obj in (_page, _browser, _playwright):
        if obj:
            try:
                await obj.close()
            except Exception:
                pass
    _browser = None
    _page = None
    _playwright = None


async def get_page(url: str, timeout: int = 60000, wait_until: str = "networkidle"):
    global _browser, _page, _playwright

    if _page:
        try:
            await _page.evaluate("1")
        except Exception:
            _page = None
            if _browser:
                try:
                    await _browser.close()
                except Exception:
                    pass
                _browser = None

    if not _browser:
        p = await async_playwright().start()
        _playwright = p
        _browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--ignore-certificate-errors",
                "--disable-web-security",
            ]
        )
        _page = await _browser.new_page()
        await _page.set_extra_http_headers({
            "Accept-Language": "es-CO,es;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })

    await _page.goto(url, wait_until=wait_until, timeout=timeout)
    await asyncio.sleep(2)
    return _page


async def new_page():
    global _browser
    if not _browser:
        raise RuntimeError("Browser not initialized")
    return await _browser.new_page()


async def browser_ready() -> bool:
    global _page
    if not _page:
        return False
    try:
        await _page.evaluate("1")
        return True
    except Exception:
        return False
