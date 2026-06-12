import os
import logging
import asyncio

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADRES_URL = "https://aplicaciones.adres.gov.co/BDUA_Internet/Pages/ConsultarAfiliadoWeb_2.aspx"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DOCUMENT_TYPES = {
    "cedula": "CC",
    "ti": "TI",
    "ce": "CE",
    "pasaporte": "PA",
    "rc": "RC",
    "nu": "NU",
    "as": "AS",
    "ms": "MS",
    "cd": "CD",
    "cn": "CN",
    "sc": "SC",
    "pe": "PE",
    "pt": "PT",
}

browser = None
page = None
playwright = None


async def get_page():
    global browser, page, playwright
    if page:
        try:
            await page.evaluate("1")
            return page
        except Exception:
            page = None

    if browser:
        try:
            await browser.close()
        except Exception:
            pass
        browser = None

    if playwright:
        try:
            await playwright.stop()
        except Exception:
            pass
        playwright = None

    p = await async_playwright().start()
    playwright = p
    browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = await browser.new_page()
    await page.goto(ADRES_URL, wait_until="networkidle", timeout=60000)
    logger.info("Navegador abierto. Resuelve el CAPTCHA en la ventana.")
    return page


async def consultar_adres(doc_type_value: str, doc_number: str) -> str:
    try:
        p = await get_page()
    except Exception as e:
        return f"Error al abrir el navegador: {e}. Usa /start"

    try:
        if await p.locator("#tipoDoc").count() == 0:
            return "No se encontró el formulario."

        await p.evaluate(f"document.getElementById('tipoDoc').value = '{doc_type_value}';")
        await p.evaluate(f"document.getElementById('txtNumDoc').value = '{doc_number}';")

        result_data = await p.evaluate("""() => {
            const btn = document.getElementById('btnConsultar');
            const form = document.forms[0];
            if (!btn || !form) return 'ERR: no form/btn';

            const fd = new FormData(form);
            fd.append(btn.name, btn.value);

            return new Promise((resolve) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', form.action, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = () => {
                    const text = xhr.responseText || '';
                    resolve('OK:' + xhr.status + ':' + text);
                };
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 25000;
                xhr.send(new URLSearchParams(fd).toString());
            });
        }""")

        if result_data.startswith('ERR:'):
            return result_data

        if result_data.startswith('OK:'):
            parts = result_data.split(':', 2)
            html = parts[2] if len(parts) > 2 else ''

            import re as _re
            m = _re.search(r"window\.open\('([^']+)", html)
            if m:
                result_url = m.group(1)
                if not result_url.startswith('http'):
                    base = ADRES_URL.rsplit('/', 1)[0]
                    result_url = base + '/' + result_url
                logger.info(f"Abriendo resultado: {result_url}")

                try:
                    await p.goto(result_url, wait_until="load", timeout=60000)
                except Exception:
                    try:
                        await p.goto(result_url, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                await asyncio.sleep(3)

                text = await p.locator("body").inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                start = next((i for i, l in enumerate(lines) if "Información Básica" in l), 0)
                end = next((i for i, l in enumerate(lines) if "Fecha de Impresión" in l), len(lines))
                data = lines[start:end+1] if end < len(lines) else lines[start:]
                return "\n".join(data[:15])

            solo_texto = _re.sub(r'<[^>]+>', ' ', html)
            solo_texto = _re.sub(r'&[^;]+;', ' ', solo_texto)
            solo_texto = _re.sub(r'\s+', ' ', solo_texto).strip()
            lines = [l.strip() for l in solo_texto.split("\n") if l.strip()]
            relevant = [l for l in lines if any(k in l.upper() for k in [
                "NOMBRE", "APELLIDO", "ESTADO", "EPS", "REGIMEN",
                "AFILIACION", "AFILIADO", "DOCUMENTO", "CEDULA",
                "IDENTIFICACION", "MUNICIPIO", "DEPARTAMENTO",
                "ACTIVO", "SUSPENDIDO", "RETIRADO", "FECHA",
                "COTIZANTE", "BENEFICIARIO", "CONTRIBUTIVO", "SUBSIDIADO",
            ])]
            if relevant:
                return "\n".join(relevant[:30])
            return solo_texto[:1500]

        return result_data

    except Exception as e:
        logger.exception("Error en consulta")
        estr = str(e)
        if "closed" in estr.lower() or "detached" in estr.lower():
            return "La ventana del navegador se cerró. Usa /start para reabrirla."
        return f"Error: {estr[:200]}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipos = ", ".join(DOCUMENT_TYPES.keys())
    await update.effective_message.reply_text(
        "Abriendo navegador para ADRES...\n\n"
        "Usá:\n"
        f"/consulta <tipo> <numero>\n\n"
        f"Tipos válidos: {tipos}\n\n"
        "Ej: /consulta cedula 888811111"
    )

    try:
        await get_page()
        await update.effective_message.reply_text(
            "Navegador listo."
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Error al abrir navegador: {e}")


async def consulta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Uso: /consulta <tipo> <numero>\nEj: /consulta cedula 888811111"
        )
        return

    doc_key = context.args[0].lower()
    doc_number = context.args[1]

    if doc_key not in DOCUMENT_TYPES:
        tipos = ", ".join(DOCUMENT_TYPES.keys())
        await update.effective_message.reply_text(f"Tipo inválido. Válidos: {tipos}")
        return

    if not doc_number.isdigit():
        await update.effective_message.reply_text("El número debe ser numérico.")
        return

    doc_value = DOCUMENT_TYPES[doc_key]
    msg = await update.effective_message.reply_text(
        f"Consultando {doc_key} {doc_number}..."
    )

    result = await consultar_adres(doc_value, doc_number)
    try:
        await msg.edit_text(result)
    except Exception:
        await update.effective_message.reply_text(result)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser, playwright, page
    for obj in (page, browser, playwright):
        if obj:
            try:
                await obj.close()
            except Exception:
                pass
    browser = None
    page = None
    playwright = None
    await update.effective_message.reply_text("Navegador cerrado.")


async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global page
    if not page:
        await update.effective_message.reply_text("No hay navegador abierto. Usa /start")
        return
    try:
        await page.evaluate("1")
        png = await page.screenshot(type="png")
        await update.effective_message.reply_photo(photo=png)
    except Exception as e:
        await update.effective_message.reply_text(f"Error: {e}")


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global page
    if not page:
        await update.effective_message.reply_text("No hay navegador. Usa /start")
        return
    try:
        await page.evaluate("1")
        title = await page.title()
        selects = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('select')).map(s => ({
                id: s.id, name: s.name, options: Array.from(s.options).map(o => ({text: o.text, value: o.value}))
            }))
        """)
        inputs = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('input[type=text], input[type=number]')).map(i => ({
                id: i.id, name: i.name, placeholder: i.placeholder
            }))
        """)
        buttons = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('input[type=submit], button')).map(b => ({
                id: b.id, type: b.type, value: b.value, text: b.innerText?.slice(0,50)
            }))
        """)
        lines = [f"Title: {title}"]
        lines.append(f"\nSELECTS ({len(selects)}):")
        for s in selects:
            lines.append(f"  id={s['id']}, opciones={s['options']}")
        lines.append(f"\nINPUTS ({len(inputs)}):")
        for i in inputs:
            lines.append(f"  id={i['id']}")
        lines.append(f"\nBOTONES ({len(buttons)}):")
        for b in buttons:
            lines.append(f"  id={b['id']}, text={b['value'] or b['text']}")
        await update.effective_message.reply_text("\n".join(lines))
    except Exception as e:
        await update.effective_message.reply_text(f"Error: {e}")


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN no configurado en .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("consulta", consulta))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("debug", debug))

    logger.info("Bot iniciado.")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        if playwright:
            asyncio.run(stop(None, None))


if __name__ == "__main__":
    main()

