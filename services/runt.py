import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

RUNT_URL = "https://www.runt.com.co/consultaCiudadana/consultaVehiculo"


async def consultar_vehiculo(placa: str) -> str:
    if not re.match(r"^[A-Za-z]{3}\d{3}$", placa):
        return "Formato de placa invalido. Debe ser ABC123"

    try:
        p = await get_page(RUNT_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con RUNT: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(placa) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('placa') || id.includes('placa') ||
                    name.includes('vehiculo') || id.includes('vehiculo') ||
                    name.includes('matricula') || id.includes('matricula'))) {{
                    i.value = placa;
                }}
            }});
        }}""", placa.upper())

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
        return _parse_runt_result(page_text, placa)

    except Exception as e:
        logger.exception("Error en consulta RUNT")
        return f"Error RUNT: {str(e)[:200]}"


async def consultar_por_documento(doc_number: str) -> str:
    try:
        p = await get_page(RUNT_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con RUNT: {e}"

    try:
        await asyncio.sleep(4)

        await p.evaluate(f"""(docNumber) => {{
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('doc') || id.includes('doc') ||
                    name.includes('ident') || id.includes('ident') ||
                    name.includes('cedula') || id.includes('cedula') ||
                    name.includes('propietario') || id.includes('propietario'))) {{
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
        return _parse_runt_result(page_text, doc_number)

    except Exception as e:
        logger.exception("Error en consulta RUNT por documento")
        return f"Error RUNT: {str(e)[:200]}"


def _parse_runt_result(text: str, query: str = "") -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text.upper() for k in [
        "NO REGISTRA", "NO SE ENCUENTRA", "SIN RESULTADOS",
        "NO EXISTE", "VEHICULO NO REGISTRADO",
    ]):
        return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
               f"\nResultado: No se encontro informacion para '{query}'\n" + "-" * 30

    vehiculos = []
    current = {}
    for line in lines:
        upper = line.upper()
        if "PLACA" in upper:
            if current and (current.get("placa") or current.get("marca")):
                vehiculos.append(current)
            current = {"placa": line}
        elif current:
            for field in [
                "MARCA", "LINEA", "MODELO", "COLOR", "CILINDRAJE",
                "SERVICIO", "CLASE", "TIPO", "MOTOR", "CHASIS",
                "VIN", "PROPIETARIO", "ORGANISMO", "ESTADO",
                "FECHA MATRICULA", "SOAT", "TECNOMECANICA",
                "PRENDAS", "LIMITACIONES",
            ]:
                if field in upper:
                    current[field.lower().replace(" ", "_")] = line
                    break

    if current and (current.get("placa") or current.get("marca")):
        vehiculos.append(current)

    if vehiculos:
        result = f"*RUNT - REGISTRO VEHICULAR* ({len(vehiculos)} encontrados)\n" + "-" * 30
        for i, v in enumerate(vehiculos[:5], 1):
            result += f"\n*Vehiculo {i}:*"
            for key, val in v.items():
                clean_val = val.split(":", 1)[-1].strip() if ":" in val else val
                result += f"\n  {key.replace('_', ' ').title()}: {clean_val}"
        result += "\n" + "-" * 30
        return result

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "PLACA", "MARCA", "MODELO", "LINEA", "COLOR",
            "CILINDRAJE", "SERVICIO", "CLASE", "MOTOR",
            "PROPIETARIO", "ESTADO", "SOAT", "TECNOMECANICA",
            "VIN", "CHASIS", "PRENDA", "LIMITACION",
            "FECHA", "ORGANISMO", "NO REGISTRA",
        ])
    ][:20]

    if relevant:
        return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*RUNT - REGISTRO VEHICULAR*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar resultado.\n\n{lines[:10]}\n" + "-" * 30
