import asyncio
import logging
import re
from urllib.parse import quote

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

RAMA_JUDICIAL_URL = (
    "https://consultaprocesos.ramajudicial.gov.co"
    "/procesos/bienvenida/consultasUnificadas.jsf"
)


async def consultar_por_nombre(nombres: str, apellidos: str = "") -> str:
    try:
        p = await get_page(RAMA_JUDICIAL_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con Rama Judicial: {e}"

    try:
        await asyncio.sleep(4)

        nombre_completo = f"{nombres} {apellidos}".strip()

        await p.evaluate(f"""(nombre) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('nombre') || name.includes('nombre') ||
                    id.includes('sujeto') || name.includes('sujeto') ||
                    id.includes('parte') || name.includes('parte'))) {{
                    i.value = nombre;
                }}
            }});
        }}""", nombre_completo)

        try:
            btns = await p.evaluate("""() => {
                const buttons = document.querySelectorAll('input[type="submit"], button, a');
                return Array.from(buttons).filter(b =>
                    b.innerText && /consultar|buscar|search/i.test(b.innerText)
                ).map(b => ({ id: b.id, selector: b.id ? '#' + b.id : null }));
            }""")
            for b in btns:
                if b["selector"]:
                    try:
                        await p.locator(b["selector"]).click(timeout=5000)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        await asyncio.sleep(5)

        page_text = await p.locator("body").inner_text()
        return _parse_rama_result(page_text)

    except Exception as e:
        logger.exception("Error en consulta Rama Judicial")
        return f"Error Rama Judicial: {str(e)[:200]}"


async def consultar_por_documento(doc_number: str) -> str:
    try:
        p = await get_page(RAMA_JUDICIAL_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con Rama Judicial: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(docNumber) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('documento') || name.includes('documento') ||
                    id.includes('ident') || name.includes('ident') ||
                    id.includes('cedula') || name.includes('cedula') ||
                    id.includes('nit') || name.includes('nit'))) {{
                    i.value = docNumber;
                }}
            }});
        }}""", doc_number)

        try:
            btns = await p.evaluate("""() => {
                const buttons = document.querySelectorAll('input[type="submit"], button, a');
                return Array.from(buttons).filter(b =>
                    b.innerText && /consultar|buscar|search/i.test(b.innerText)
                ).map(b => ({ id: b.id, selector: b.id ? '#' + b.id : null }));
            }""")
            for b in btns:
                if b["selector"]:
                    try:
                        await p.locator(b["selector"]).click(timeout=5000)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        await asyncio.sleep(5)

        page_text = await p.locator("body").inner_text()
        return _parse_rama_result(page_text)

    except Exception as e:
        logger.exception("Error en consulta Rama Judicial por documento")
        return f"Error Rama Judicial: {str(e)[:200]}"


async def consultar_por_proceso(numero_proceso: str) -> str:
    try:
        p = await get_page(RAMA_JUDICIAL_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con Rama Judicial: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(numProceso) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const id = (i.id || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                if (!i.value && (id.includes('proceso') || name.includes('proceso') ||
                    id.includes('radic') || name.includes('radic') ||
                    id.includes('numero') || name.includes('numero'))) {{
                    i.value = numProceso;
                }}
            }});
        }}""", numero_proceso)

        try:
            btns = await p.evaluate("""() => {
                const buttons = document.querySelectorAll('input[type="submit"], button, a');
                return Array.from(buttons).filter(b =>
                    b.innerText && /consultar|buscar|search/i.test(b.innerText)
                ).map(b => ({ id: b.id, selector: b.id ? '#' + b.id : null }));
            }""")
            for b in btns:
                if b["selector"]:
                    try:
                        await p.locator(b["selector"]).click(timeout=5000)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        await asyncio.sleep(5)

        page_text = await p.locator("body").inner_text()
        return _parse_rama_result(page_text)

    except Exception as e:
        logger.exception("Error en consulta Rama Judicial por proceso")
        return f"Error Rama Judicial: {str(e)[:200]}"


def _parse_rama_result(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text.upper() for k in [
        "NO SE ENCONTRARON", "NO HAY RESULTADOS", "SIN RESULTADOS",
        "CERO RESULTADOS", "NO EXISTEN", "NO SE ENCUENTRA"
    ]):
        return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
               "\nResultado: No se encontraron procesos judiciales\n" + "-" * 30

    procesos = []
    current = {}
    for line in lines:
        upper = line.upper()
        if "RADICACION" in upper or "RADICADO" in upper or "PROCESO" in upper:
            if current and current.get("radicado"):
                procesos.append(current)
            current = {"radicado": line}
        elif current:
            if "DESPACHO" in upper or "JUZGADO" in upper:
                current["despacho"] = line
            elif "DEMANDANTE" in upper or "ACCIONANTE" in upper:
                current["demandante"] = line
            elif "DEMANDADO" in upper or "ACCIONADO" in upper:
                current["demandado"] = line
            elif "CLASE" in upper or "TIPO" in upper:
                current["clase"] = line
            elif "ESTADO" in upper:
                current["estado"] = line
            elif "FECHA" in upper:
                current["fecha"] = line
            elif "PONENTE" in upper or "MAGISTRADO" in upper:
                current["ponente"] = line
    if current and current.get("radicado"):
        procesos.append(current)

    if procesos:
        result = f"*RAMA JUDICIAL - PROCESOS* ({len(procesos)} encontrados)\n" + "-" * 30
        for i, proc in enumerate(procesos[:10], 1):
            result += f"\n*Proceso {i}:*"
            for key, val in proc.items():
                result += f"\n  {key.title()}: {val.split(':', 1)[-1].strip() if ':' in val else val}"
        result += "\n" + "-" * 30
        return result

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "RADICADO", "RADICACION", "PROCESO", "JUZGADO",
            "DESPACHO", "DEMANDANTE", "DEMANDADO", "ESTADO",
            "FECHA", "PONENTE", "CLASE", "ACTUACION",
        ])
    ][:25]

    if relevant:
        return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*RAMA JUDICIAL - PROCESOS*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar resultado.\n\n{lines[:10]}\n" + "-" * 30
