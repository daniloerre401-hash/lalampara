import os
import logging
import asyncio

from twocaptcha import TwoCaptcha

logger = logging.getLogger(__name__)

_captcha_api_key = None


def get_api_key():
    global _captcha_api_key
    if _captcha_api_key is None:
        _captcha_api_key = os.getenv("CAPTCHA_API_KEY", "")
    return _captcha_api_key


async def solve_recaptcha_v2(page, site_key: str) -> str:
    api_key = get_api_key()
    if not api_key:
        logger.warning("CAPTCHA_API_KEY no configurada")
        return ""

    try:
        solver = TwoCaptcha(api_key)
        result = solver.recaptcha(
            sitekey=site_key,
            url=page.url,
        )
        token = result.get("code", "")
        if token:
            logger.info("reCAPTCHA v2 resuelto")
        return token
    except Exception as e:
        logger.warning(f"Error reCAPTCHA: {e}")
        return ""


async def inyectar_token_y_submit(page, token: str) -> bool:
    try:
        await page.evaluate(f"""() => {{
            const ta = document.getElementById('g-recaptcha-response');
            if (ta) {{
                ta.value = '{token}';
                ta.style.display = 'block';
            }}

            const captchaDiv = document.querySelector('#captchaAntecedentes textarea');
            if (captchaDiv) {{
                captchaDiv.value = '{token}';
            }}

            if (typeof grecaptcha !== 'undefined') {{
                try {{
                    const id = grecaptcha.render(document.querySelector('#captchaAntecedentes'), {{
                        sitekey: document.querySelector('iframe[src*="recaptcha"]')?.src?.match(/k=([^&]+)/)?.[1] || ''
                    }});
                }} catch(e) {{}}
            }}
        }}""")

        await page.evaluate(f"""() => {{
            const ta = document.querySelector('textarea[name="g-recaptcha-response"]');
            if (ta) ta.value = '{token}';
        }}""")

        return True
    except Exception as e:
        logger.warning(f"Error inyectando token: {e}")
        return False


async def solve_image_captcha(page, img_selector: str, input_selector: str) -> bool:
    api_key = get_api_key()
    if not api_key:
        return False
    try:
        img = page.locator(img_selector)
        if await img.count() == 0:
            return False
        import base64
        img_bytes = await img.screenshot(type="png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        solver = TwoCaptcha(api_key)
        result = solver.normal(img_b64)
        captcha_text = result.get("code", "")
        if captcha_text:
            await page.locator(input_selector).fill(captcha_text)
            logger.info("Image CAPTCHA solved")
            return True
    except Exception as e:
        logger.warning(f"Error image captcha: {e}")
    return False
