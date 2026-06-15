import asyncio
import logging
import re

from .browser_manager import get_page

logger = logging.getLogger(__name__)

RAMA_URL = "https://consultaprocesos.ramajudicial.gov.co/procesos/bienvenida/consultasUnificadas.jsf"


async def consultar_por_documento(doc_number: str) -> str:
    try:
        p = await get_page(RAMA_URL, timeout=60000)
    except Exception as e:
        return f"Rama Judicial error conexion: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(doc) => {{
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            for (let i of inputs) {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('documento') || name.includes('documento') ||
                    id.includes('ident') || name.includes('ident'))) {{
                    i.value = doc;
                    break;
                }}
            }}
        }}""", doc_number)

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, input[type=submit]');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText || b.value)) {
                    b.click(); break;
                }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, doc_number)

    except Exception as e:
        logger.exception("Rama Judicial error")
        return f"Rama Judicial error: {str(e)[:200]}\n\nLink directo: {RAMA_URL}"


async def consultar_por_nombre(nombres: str, apellidos: str = "") -> str:
    try:
        p = await get_page(RAMA_URL, timeout=60000)
    except Exception as e:
        return f"Rama Judicial error conexion: {e}"

    try:
        await asyncio.sleep(4)
        nombre_completo = f"{nombres} {apellidos}".strip()

        await p.evaluate(f"""(nombre) => {{
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            for (let i of inputs) {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('nombre') || name.includes('nombre') ||
                    id.includes('sujeto') || name.includes('sujeto'))) {{
                    i.value = nombre;
                    break;
                }}
            }}
        }}""", nombre_completo)

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, input[type=submit]');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText || b.value)) {
                    b.click(); break;
                }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, nombre_completo)

    except Exception as e:
        logger.exception("Rama Judicial error")
        return f"Rama Judicial error: {str(e)[:200]}"


async def consultar_por_proceso(numero_proceso: str) -> str:
    try:
        p = await get_page(RAMA_URL, timeout=60000)
    except Exception as e:
        return f"Rama Judicial error conexion: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(proceso) => {{
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            for (let i of inputs) {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('proceso') || name.includes('proceso') ||
                    id.includes('radic') || name.includes('radic'))) {{
                    i.value = proceso;
                    break;
                }}
            }}
        }}""", numero_proceso)

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, input[type=submit]');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText || b.value)) {
                    b.click(); break;
                }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, numero_proceso)

    except Exception as e:
        logger.exception("Rama Judicial error")
        return f"Rama Judicial error: {str(e)[:200]}"


def _parse(text: str, query: str = "") -> str:
    text_upper = text.upper()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Verificar sin resultados primero
    if any(k in text_upper for k in [
        "NO SE ENCONTRARON", "NO HAY RESULTADOS", "SIN RESULTADOS",
        "0 RESULTADOS", "NO EXISTEN", "NO SE ENCONTRO",
    ]):
        return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
               "\nSin procesos judiciales registrados\n" + "-" * 30

    # Filtrar lineas que son solo headers de pagina
    headers = {"CONSULTA DE PROCESOS", "CONSEJO DE ESTADO", "CONSEJO SUPERIOR",
               "INICIO", "CONTACTENOS", "RAMA JUDICIAL", "CONSULTA PROCESOS"}
    data_lines = [l for l in lines if l.strip().upper() not in headers and l.strip().upper() not in headers]

    keywords = [
        "RADICADO", "RADICACION", "JUZGADO",
        "DESPACHO", "DEMANDANTE", "DEMANDADO", "ESTADO",
        "FECHA", "PONENTE", "CLASE", "ACTUACION",
        "ACCIONANTE", "ACCIONADO", "SENTENCIA",
    ]
    relevant = [l for l in data_lines if any(k in l.upper() for k in keywords)][:25]

    if relevant:
        return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
           "\nSin procesos judiciales registrados para esta consulta\n" + "-" * 30
