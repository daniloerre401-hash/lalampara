import asyncio
import logging
import os
import re

from .browser_manager import get_page, new_page
from . import captcha as cap

logger = logging.getLogger(__name__)

SIMIT_URL = "https://www.fcm.org.co/simit/"
_logged_in = False


async def _login(p) -> bool:
    global _logged_in
    if _logged_in:
        return True

    email = os.getenv("SIMIT_EMAIL", "")
    password = os.getenv("SIMIT_PASSWORD", "")
    if not email or not password:
        return False

    try:
        await p.goto(SIMIT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, a');
            for (let b of btns) {
                if (b.innerText && b.innerText.trim().toUpperCase() === 'INGRESAR') { b.click(); return; }
            }
        }""")
        await asyncio.sleep(3)

        await p.evaluate(f"""() => {{
            document.getElementById('emailIS').value = '{email}';
            document.getElementById('passwordIS').value = '{password}';
        }}""")
        await asyncio.sleep(1)
        await p.evaluate("document.getElementById('btnLogin').click()")
        await asyncio.sleep(5)

        if "home-public" in p.url:
            _logged_in = True
            logger.info("SIMIT login OK")
            return True
        return False
    except Exception as e:
        logger.warning(f"SIMIT login: {e}")
        return False


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(SIMIT_URL, timeout=30000)
    except Exception:
        try:
            p = await new_page()
            await p.goto(SIMIT_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            return f"SIMIT error conexion: {e}"

    try:
        if not _logged_in:
            ok = await _login(p)
            if not ok:
                return (
                    "SIMIT: login fallido.\n"
                    "Configura SIMIT_EMAIL y SIMIT_PASSWORD en .env"
                )

        # Go to estado-cuenta
        await p.goto(f"{SIMIT_URL}#/estado-cuenta", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)

        # Fill the form
        await p.evaluate(f"""() => {{
            const inp = document.getElementById('txtBusqueda');
            if (inp) {{
                inp.value = '{doc_number}';
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        }}""")
        await asyncio.sleep(2)

        # Click submit - this triggers reCAPTCHA
        await p.evaluate("""() => {
            const btn = document.getElementById('btnNumDocPlaca');
            if (btn) btn.click();
        }""")
        await asyncio.sleep(4)

        # Find and solve reCAPTCHA
        sitekey = await _get_sitekey(p)
        if not sitekey:
            return "SIMIT: no se encontro reCAPTCHA. Link manual: " + SIMIT_URL

        token = await cap.solve_recaptcha_v2(p, sitekey)
        if not token:
            return "SIMIT: reCAPTCHA no resuelto. Verifica CAPTCHA_API_KEY"

        # Inject token and trigger callback
        await p.evaluate(f"""() => {{
            const ta = document.querySelector('textarea[name="g-recaptcha-response"]');
            if (ta) ta.value = '{token}';
        }}""")

        # The reCAPTCHA callback should auto-submit. Wait for results.
        await asyncio.sleep(8)

        body = await p.locator("body").inner_text()
        return _parse(body, doc_number)

    except Exception as e:
        logger.exception("SIMIT error")
        return f"SIMIT error: {str(e)[:200]}"


async def _get_sitekey(p) -> str | None:
    return await p.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe[src*="recaptcha"]');
        for (let f of iframes) {
            const m = f.src.match(/[?&]k=([^&]+)/);
            if (m) return m[1];
        }
        const html = document.documentElement.innerHTML;
        const m = html.match(/6L[a-zA-Z0-9_-]{30,}/);
        if (m) return m[0];
        return null;
    }""")


def _parse(text: str, query: str = "") -> str:
    t = text.upper()

    if any(k in t for k in [
        "NO REGISTRA", "NO TIENE MULTAS", "SIN MULTAS",
        "PAZ Y SALVO", "NO ADEUDA", "NO PRESENTA",
    ]):
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\nPaz y salvo: No registra multas\n" + "-" * 30

    if any(k in t for k in ["COMPARENDO", "MULTA", "INFRACCION"]):
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l) < 120]
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\n" + "\n".join(lines[:30]) + "\n" + "-" * 30

    return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
           "\nSin resultados. Consulte en simit.org.co\n" + "-" * 30
