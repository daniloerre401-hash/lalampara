import asyncio
import logging
import re

from .browser_manager import get_page

logger = logging.getLogger(__name__)

RUES_URLS = [
    "https://www.rues.com.co/RUES_Web/Consultas/ConsultarPersona",
    "https://www.rues.com.co/",
]


async def consultar_empresa(doc_number: str) -> str:
    last_error = ""
    for url in RUES_URLS:
        try:
            p = await get_page(url, timeout=30000)
            await asyncio.sleep(6)

            if await p.evaluate("() => document.body.innerText.length < 300"):
                last_error = "RUES: pagina no cargo correctamente."
                continue

            await p.evaluate(f"""(docNumber) => {{
                const inputs = document.querySelectorAll('input[type=text], input:not([type])');
                for (let i of inputs) {{
                    const name = (i.name || '').toLowerCase();
                    const id = (i.id || '').toLowerCase();
                    if (!i.value && (name.includes('doc') || id.includes('doc') ||
                        name.includes('ident') || id.includes('ident') ||
                        name.includes('cedula') || id.includes('cedula') ||
                        name.includes('nit') || id.includes('nit') ||
                        name.includes('numero') || id.includes('numero'))) {{
                        i.value = docNumber; break;
                    }}
                }}
            }}""", doc_number)

            await p.evaluate("""() => {
                const btns = document.querySelectorAll('button, input[type=submit], a.btn');
                for (let b of btns) {
                    if (/consultar|buscar/i.test(b.innerText || b.value || '')) {
                        b.click(); break;
                    }
                }
            }""")
            await asyncio.sleep(5)

            text = await p.locator("body").inner_text()
            return _parse(text, doc_number)

        except Exception as e:
            last_error = f"RUES error: {str(e)[:100]}"
            continue

    return last_error or "RUES: no se pudo acceder. Consulte manualmente en rues.com.co"


async def consultar_por_nombre(nombre: str) -> str:
    try:
        p = await get_page(RUES_URLS[0], timeout=30000)
        await asyncio.sleep(6)

        await p.evaluate(f"""(nombre) => {{
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            for (let i of inputs) {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('nombre') || id.includes('nombre') ||
                    name.includes('razon') || id.includes('razon') ||
                    name.includes('empresa') || id.includes('empresa'))) {{
                    i.value = nombre; break;
                }}
            }}
        }}""", nombre)

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, input[type=submit], a.btn');
            for (let b of btns) {
                if (/consultar|buscar/i.test(b.innerText || b.value || '')) {
                    b.click(); break;
                }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, nombre)

    except Exception as e:
        logger.exception("RUES error")
        return f"RUES error: {str(e)[:200]}"


def _parse(text: str, query: str = "") -> str:
    text_upper = text.upper()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text_upper for k in [
        "NO REGISTRA", "NO SE ENCUENTRA", "SIN RESULTADOS",
        "NO EXISTE", "NO HAY DATOS",
    ]):
        return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
               f"\nNo se encontro registro para '{query}'\n" + "-" * 30

    keywords = [
        "NIT", "MATRICULA", "RAZON", "RAZON SOCIAL", "ESTADO",
        "RENOVACION", "DIRECCION", "MUNICIPIO", "ACTIVIDAD",
        "CATEGORIA", "REPRESENTANTE", "FECHA", "SOCIEDAD",
        "COMERCIANTE", "ESTABLECIMIENTO", "NO REGISTRA",
    ]
    relevant = [l for l in lines if any(k in l.upper() for k in keywords)][:20]

    if relevant:
        return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
           "\nNo se pudo interpretar. Consulte en rues.com.co\n" + "-" * 30
