import asyncio
import logging
import re

from .browser_manager import get_page, new_page

logger = logging.getLogger(__name__)

RUNT_URL = "https://www.runt.com.co/consultaCiudadana/consultaVehiculo"

RUNT_DOC_TYPES = {
    "cc": "CEDULA_CIUDADANIA", "cedula": "CEDULA_CIUDADANIA",
    "ce": "CEDULA_EXTRANJERIA", "extranjeria": "CEDULA_EXTRANJERIA",
    "ti": "TARJETA_IDENTIDAD", "tarjeta": "TARJETA_IDENTIDAD",
    "nit": "NIT",
    "pasaporte": "PASAPORTE", "pa": "PASAPORTE",
}


async def consultar_vehiculo(placa: str) -> str:
    if not re.match(r"^[A-Za-z]{3}\d{3}$", placa):
        return "Formato placa invalido (ABC123)"

    try:
        p = await get_page(RUNT_URL, timeout=60000)
    except Exception as e:
        return f"RUNT error conexion: {e}"

    try:
        await asyncio.sleep(5)

        inputs = await p.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[id^=mat-input]')).map(i => ({
                id: i.id, index: parseInt(i.id.replace('mat-input-', ''))
            }));
        }""")

        if len(inputs) < 2:
            return "RUNT: formulario no encontrado. La pagina puede haber cambiado."

        try:
            await p.locator(f"#{inputs[0]['id']}").fill(placa.upper())
        except Exception:
            await p.evaluate(f"document.getElementById('{inputs[0]['id']}').value = '{placa.upper()}'")

        captcha_solved = False
        if len(inputs) >= 3:
            captcha_solved = await _solve_runt_captcha(p)

        if not captcha_solved and len(inputs) >= 3:
            return "RUNT: CAPTCHA detectado. Configura CAPTCHA_API_KEY en .env o consulta manualmente en " + RUNT_URL

        btn = await p.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText)) return b.id || b.className || 'found';
            }
            return null;
        }""")
        if btn:
            try:
                await p.locator("button").filter(has_text="Consultar").first.click(timeout=5000)
            except Exception:
                await p.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    for (let b of btns) {
                        if (/consultar|buscar/i.test(b.innerText)) { b.click(); break; }
                    }
                }""")

        await asyncio.sleep(5)
        text = await p.locator("body").inner_text()
        return _parse(text, placa)

    except Exception as e:
        logger.exception("RUNT error")
        return f"RUNT error: {str(e)[:200]}"


async def consultar_por_documento(doc_number: str) -> str:
    if not doc_number.isdigit():
        return "El documento debe ser numerico."

    try:
        p = await get_page(RUNT_URL, timeout=60000)
    except Exception as e:
        return f"RUNT error conexion: {e}"

    try:
        await asyncio.sleep(5)

        inputs = await p.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[id^=mat-input]')).map(i => ({
                id: i.id, index: parseInt(i.id.replace('mat-input-', ''))
            }));
        }""")

        if len(inputs) < 2:
            return "RUNT: formulario no encontrado."

        try:
            await p.locator(f"#{inputs[0]['id']}").fill(doc_number)
        except Exception:
            await p.evaluate(f"document.getElementById('{inputs[0]['id']}').value = '{doc_number}'")

        captcha_solved = False
        if len(inputs) >= 3:
            captcha_solved = await _solve_runt_captcha(p)

        if not captcha_solved and len(inputs) >= 3:
            return "RUNT: CAPTCHA detectado. Configura CAPTCHA_API_KEY en .env"

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText)) { b.click(); break; }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, doc_number)

    except Exception as e:
        logger.exception("RUNT error")
        return f"RUNT error: {str(e)[:200]}"


async def _solve_runt_captcha(p) -> bool:
    from . import captcha as cap
    try:
        imgs = await p.evaluate("""() => {
            return Array.from(document.querySelectorAll('img')).filter(i =>
                i.width > 50 && i.height > 20 && i.src && !i.src.includes('logo')
            ).map(i => ({src: i.src.slice(0, 100), id: i.id, className: i.className}))
        }""")
        for img in imgs:
            img_id = img.get("id") or img.get("className")
            if img_id and await p.locator(f"#{img_id}").count() > 0:
                solved = await cap.solve_image_captcha(p, f"#{img_id}", "input[id*=mat-input]:last-of-type")
                if solved:
                    return True
            elif img.get("className") and await p.locator(f".{img['className'].split()[0]}").count() > 0:
                sel = "." + img["className"].split()[0]
                solved = await cap.solve_image_captcha(p, sel, "input[id*=mat-input]:last-of-type")
                if solved:
                    return True
        return False
    except Exception:
        return False


def _parse(text: str, query: str = "") -> str:
    text_upper = text.upper()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text_upper for k in [
        "NO REGISTRA", "NO SE ENCUENTRA", "SIN RESULTADOS",
        "NO EXISTE", "VEHICULO NO", "NO HAY DATOS",
    ]):
        return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
               f"\nNo se encontro informacion para '{query}'\n" + "-" * 30

    keywords = [
        "PLACA", "MARCA", "MODELO", "LINEA", "COLOR", "CILINDRAJE",
        "SERVICIO", "CLASE", "MOTOR", "PROPIETARIO", "ESTADO",
        "SOAT", "TECNOMECANICA", "VIN", "CHASIS", "PRENDA",
        "LIMITACION", "FECHA", "ORGANISMO", "NO REGISTRA",
        "DOCUMENTO", "NOMBRE", "CEDULA", "ESTADO VEHICULO",
    ]
    relevant = [l for l in lines if any(k in l.upper() for k in keywords)]

    if relevant:
        return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant[:25]) + "\n" + "-" * 30

    return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar resultado.\n{lines[:8]}\n" + "-" * 30
