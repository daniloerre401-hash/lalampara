import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

RUES_URL = "https://www.rues.com.co/RUES_Web/Consultas/ConsultarPersona"


async def consultar_empresa(doc_number: str) -> str:
    try:
        p = await get_page(RUES_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con RUES: {e}"

    try:
        await asyncio.sleep(6)

        await p.evaluate(f"""(docNumber) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('doc') || id.includes('doc') ||
                    name.includes('ident') || id.includes('ident') ||
                    name.includes('cedula') || id.includes('cedula') ||
                    name.includes('nit') || id.includes('nit') ||
                    name.includes('numero') || id.includes('numero'))) {{
                    i.value = docNumber;
                }}
            }});
        }}""", doc_number)

        btns = await p.evaluate("""() => {
            const buttons = document.querySelectorAll('input[type="submit"], button, a');
            return Array.from(buttons).filter(b =>
                b.innerText && /consultar|buscar|search|aceptar/i.test(b.innerText)
            ).map(b => ({ id: b.id, selector: b.id ? '#' + b.id : null }));
        }""")
        for b in btns:
            if b["selector"]:
                try:
                    await p.locator(b["selector"]).click(timeout=5000)
                    break
                except Exception:
                    pass

        await asyncio.sleep(5)

        page_text = await p.locator("body").inner_text()
        return _parse_rues_result(page_text, doc_number)

    except Exception as e:
        logger.exception("Error en consulta RUES")
        return f"Error RUES: {str(e)[:200]}"


async def consultar_por_nombre(nombre: str) -> str:
    try:
        p = await get_page(RUES_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con RUES: {e}"

    try:
        await asyncio.sleep(6)

        await p.evaluate(f"""(nombre) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('nombre') || id.includes('nombre') ||
                    name.includes('razon') || id.includes('razon') ||
                    name.includes('empresa') || id.includes('empresa') ||
                    name.includes('comerciante') || id.includes('comerciante'))) {{
                    i.value = nombre;
                }}
            }});
        }}""", nombre)

        btns = await p.evaluate("""() => {
            const buttons = document.querySelectorAll('input[type="submit"], button, a');
            return Array.from(buttons).filter(b =>
                b.innerText && /consultar|buscar|search|aceptar/i.test(b.innerText)
            ).map(b => ({ id: b.id, selector: b.id ? '#' + b.id : null }));
        }""")
        for b in btns:
            if b["selector"]:
                try:
                    await p.locator(b["selector"]).click(timeout=5000)
                    break
                except Exception:
                    pass

        await asyncio.sleep(5)

        page_text = await p.locator("body").inner_text()
        return _parse_rues_result(page_text, nombre)

    except Exception as e:
        logger.exception("Error en consulta RUES por nombre")
        return f"Error RUES: {str(e)[:200]}"


def _parse_rues_result(text: str, query: str = "") -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text.upper() for k in [
        "NO REGISTRA", "NO SE ENCUENTRA", "SIN RESULTADOS",
        "NO EXISTE", "NO HAY DATOS",
    ]):
        return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
               f"\nResultado: No se encontro registro mercantil para '{query}'\n" + "-" * 30

    empresas = []
    current = {}
    for line in lines:
        upper = line.upper()
        if "NIT" in upper or "MATRICULA" in upper or "RAZON" in upper or "NOMBRE" in upper:
            if current and (current.get("nit") or current.get("razon_social") or current.get("matricula")):
                empresas.append(current)
            current = {}
            if "NIT" in upper:
                current["nit"] = line
            elif "MATRICULA" in upper:
                current["matricula"] = line
            elif "RAZON" in upper:
                current["razon_social"] = line
            elif "NOMBRE" in upper:
                current["nombre"] = line
        elif current:
            for field in [
                "RAZON SOCIAL", "MATRICULA", "ESTADO", "FECHA RENOVACION",
                "FECHA MATRICULA", "ORGANIZACION", "CATEGORIA",
                "DIRECCION", "MUNICIPIO", "ACTIVIDAD", "CIUU",
                "TIPO SOCIEDAD", "REPRESENTANTE",
            ]:
                if field in upper:
                    current[field.lower().replace(" ", "_")] = line
                    break

    if current and (current.get("nit") or current.get("razon_social") or current.get("matricula")):
        empresas.append(current)

    if empresas:
        result = f"*RUES - REGISTRO MERCANTIL* ({len(empresas)} encontrados)\n" + "-" * 30
        for i, emp in enumerate(empresas[:10], 1):
            result += f"\n*Registro {i}:*"
            for key, val in emp.items():
                clean_val = val.split(":", 1)[-1].strip() if ":" in val else val
                result += f"\n  {key.replace('_', ' ').title()}: {clean_val}"
        result += "\n" + "-" * 30
        return result

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "NIT", "MATRICULA", "RAZON", "ESTADO", "RENOVACION",
            "DIRECCION", "MUNICIPIO", "ACTIVIDAD", "CATEGORIA",
            "REPRESENTANTE", "FECHA", "SOCIEDAD", "NO REGISTRA",
            "COMERCIANTE", "ESTABLECIMIENTO",
        ])
    ][:20]

    if relevant:
        return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*RUES - REGISTRO MERCANTIL*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar resultado.\n\n{lines[:10]}\n" + "-" * 30
