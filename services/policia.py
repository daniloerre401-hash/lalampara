import asyncio
import logging
import re

from .browser_manager import get_page
from . import captcha as cap

logger = logging.getLogger(__name__)

POLICIA_URL = "https://antecedentes.policia.gov.co:7005/WebJudicial/"


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(POLICIA_URL, timeout=45000)
    except Exception as e:
        return f"Policia error conexion: {e}"

    try:
        await asyncio.sleep(3)

        await _aceptar_terminos(p)

        if "antecedentes.xhtml" not in p.url:
            return "Policia: no se pudo avanzar a la pagina de consulta."

        tiene_form = await p.evaluate("""() => ({
            tipo: !!document.getElementById('cedulaTipo'),
            input: !!document.getElementById('cedulaInput')
        })""")
        if not tiene_form["tipo"] or not tiene_form["input"]:
            return "Policia: formulario no encontrado."

        doc_value = _map_doc_type(doc_type)
        await p.evaluate(
            f"document.getElementById('cedulaTipo').value = '{doc_value}';"
        )
        await p.evaluate(
            f"document.getElementById('cedulaInput').value = '{doc_number}';"
        )

        # Solve reCAPTCHA with dynamic sitekey detection
        sitekey = await _get_sitekey(p)
        if not sitekey:
            return "Policia: no se encontro reCAPTCHA en la pagina."

        token = await cap.solve_recaptcha_v2(p, sitekey)
        if not token:
            return (
                "Policia: reCAPTCHA no resuelto.\n"
                "Verifica tu CAPTCHA_API_KEY en .env\n"
                "Link manual: " + POLICIA_URL
            )

        await cap.inyectar_token_y_submit(p, token)

        await asyncio.sleep(1)

        try:
            await p.locator("#j_idt17").click(timeout=5000)
        except Exception:
            await p.evaluate("document.getElementById('j_idt17')?.click()")

        await asyncio.sleep(6)

        body = await p.locator("body").inner_text()
        return _parse(body, doc_number)

    except Exception as e:
        logger.exception("Policia error")
        return f"Policia error: {str(e)[:200]}"


async def _aceptar_terminos(p) -> None:
    try:
        await p.locator("label[for=\"aceptaOption:0\"]").click(timeout=5000)
    except Exception:
        try:
            await p.evaluate("""() => {
                document.querySelector('label[for="aceptaOption:0"]').click();
            }""")
        except Exception:
            pass
    await asyncio.sleep(2)
    try:
        await p.locator("#continuarBtn").click(timeout=5000)
    except Exception:
        try:
            await p.evaluate("""() => {
                const btn = document.getElementById('continuarBtn');
                if (btn) { btn.disabled = false; btn.removeAttribute('disabled'); btn.click(); }
            }""")
        except Exception:
            pass
    await asyncio.sleep(4)


def _map_doc_type(doc_type: str) -> str:
    m = {
        "cc": "cc", "cedula": "cc",
        "ce": "cx", "extranjeria": "cx",
        "pa": "pa", "pasaporte": "pa",
        "dp": "dp",
    }
    return m.get(doc_type, "cc")


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

    if "DEBE SELECCIONAR" in t and "CAPTCHA" in t:
        return "Policia: reCAPTCHA no validado."

    doc_num = re.search(r'(?:C[e\u00E9]dula|Documento).*?[Nn]\u00B0?\s*(\d+)', text)
    doc_num = doc_num.group(1) if doc_num else query

    nombres = re.search(r'(?:Apellidos y Nombres|Nombres y Apellidos)[:\s]+([A-Z\u00C0-\u024F\s]+?)(?:\s{2,}|,|\.)', text)
    nombres = nombres.group(1).strip() if nombres else ""

    fecha = re.search(r'(\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM|a\.m\.|p\.m\.).*?horas del\s*\d{1,2}/\d{1,2}/\d{4})', text)
    fecha = fecha.group(1) if fecha else ""

    no_tiene = any(k in t for k in [
        "NO TIENE ASUNTOS PENDIENTES",
        "NO REGISTRA ANTECEDENTES",
        "NO TIENE ANTECEDENTES",
        "SIN ANTECEDENTES",
        "NO PRESENTA ANTECEDENTES",
    ])

    si_tiene = any(k in t for k in [
        "TIENE ASUNTOS PENDIENTES",
        "REGISTRA ANTECEDENTES",
        "TIENE ANTECEDENTES",
    ])

    result = "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n"
    result += "-" * 35 + "\n"

    if doc_num:
        result += f"Documento: {doc_num}\n"
    if nombres:
        result += f"Nombre: {nombres}\n"
    if fecha:
        result += f"Fecha consulta: {fecha}\n"

    result += "\n"

    if no_tiene:
        result += "Resultado: NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES\n"
    elif si_tiene:
        result += "ATENCION: REGISTRA ANTECEDENTES JUDICIALES\n"

        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"&nbsp;", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        lines = [l.strip() for l in clean.split("\n") if l.strip()]
        keywords = [
            "ANTECEDENTE", "DELITO", "FECHA", "JUZGADO",
            "SENTENCIA", "REGISTRA", "AUTORIDAD",
            "PROCESO", "CONDENA",
        ]
        relevant = [l for l in lines if any(k in l.upper() for k in keywords)][:15]
        if relevant:
            result += "\n" + "\n".join(relevant) + "\n"
    else:
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"&nbsp;", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        lines = [l.strip() for l in clean.split("\n") if l.strip()]
        relevant = [
            l for l in lines
            if 10 < len(l) < 200
            and "INICIO" not in l.upper()
            and "DIRECCION" not in l.upper()
            and "ATENCION" not in l.upper()
            and "LINEA" not in l.upper()
            and "E-MAIL" not in l.upper()
            and "PRESIDENCIA" not in l.upper()
            and "MINISTERIO" not in l.upper()
            and "CONTRATACION" not in l.upper()
            and "GOV.CO" not in l.upper()
            and "DERECHOS" not in l.upper()
            and "VOLVER" not in l.upper()
        ][:10]
        if relevant:
            result += "\n" + "\n".join(relevant) + "\n"

    result += "-" * 35
    return result
