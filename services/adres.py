import asyncio
import logging
import re

from .browser_manager import get_page

logger = logging.getLogger(__name__)

ADRES_URL = "https://aplicaciones.adres.gov.co/BDUA_Internet/Pages/ConsultarAfiliadoWeb_2.aspx"

DOCUMENT_TYPES = {
    "cedula": "CC", "ti": "TI", "ce": "CE", "pasaporte": "PA",
    "rc": "RC", "nu": "NU", "as": "AS", "ms": "MS",
    "cd": "CD", "cn": "CN", "sc": "SC", "pe": "PE", "pt": "PT",
}


async def consultar(doc_type_value: str, doc_number: str) -> str:
    try:
        p = await get_page(ADRES_URL)
    except Exception as e:
        return f"ADRES error conexion: {e}"

    try:
        if await p.locator("#tipoDoc").count() == 0:
            await p.goto(ADRES_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            if await p.locator("#tipoDoc").count() == 0:
                return "ADRES: formulario no encontrado (sitio caido)"

        await p.evaluate(f"document.getElementById('tipoDoc').value = '{doc_type_value}';")
        await p.evaluate(f"document.getElementById('txtNumDoc').value = '{doc_number}';")

        result_data = await p.evaluate("""() => {
            const btn = document.getElementById('btnConsultar');
            const form = document.forms[0];
            if (!btn || !form) return 'ERR:no_form';
            const fd = new FormData(form);
            fd.append(btn.name, btn.value);
            return new Promise((resolve) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', form.action, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = () => resolve('OK:' + xhr.status + ':' + (xhr.responseText || ''));
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 25000;
                xhr.send(new URLSearchParams(fd).toString());
            });
        }""")

        if result_data.startswith("ERR:"):
            return f"ADRES error: {result_data.replace('ERR:', '')}"

        if result_data.startswith("OK:"):
            parts = result_data.split(":", 2)
            status_code = parts[1] if len(parts) > 1 else "?"
            html = parts[2] if len(parts) > 2 else ""
            if status_code != "200":
                return f"ADRES respondio HTTP {status_code}"

            m = re.search(r"window\.open\('([^']+)", html)
            if m:
                result_url = m.group(1)
                if not result_url.startswith("http"):
                    base = ADRES_URL.rsplit("/", 1)[0]
                    result_url = base + "/" + result_url
                try:
                    await p.goto(result_url, wait_until="load", timeout=60000)
                except Exception:
                    try:
                        await p.goto(result_url, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                await asyncio.sleep(3)
                return await _parse(p)
            return _parse_fallback(html)
        return str(result_data)

    except Exception as e:
        logger.exception("ADRES error")
        estr = str(e)
        if "closed" in estr.lower():
            return "ADRES: navegador cerrado. Usa /start"
        return f"ADRES error: {estr[:200]}"


async def _parse(p) -> str:
    # Extraer solo las tablas de datos (Informacion Basica y Datos de afiliacion)
    tables = await p.evaluate("""() => {
        const result = [];
        const allTables = document.querySelectorAll('table');
        allTables.forEach(table => {
            const rows = [];
            const trs = table.querySelectorAll('tr');
            trs.forEach(tr => {
                const cells = [];
                const tds = tr.querySelectorAll('td, th');
                tds.forEach(td => cells.push(td.innerText.trim().replace(/\\s+/g, ' ')));
                if (cells.length > 1) rows.push(cells);
            });
            if (rows.length > 0 && rows.length <= 10) result.push(rows);
        });
        return result;
    }""")

    lines = ["*ADRES - CONSULTA AFILIADO*", "-" * 30]

    if tables:
        for table in tables:
            if len(table) == 0:
                continue
            headers = table[0]
            for row in table[1:]:
                for i, cell in enumerate(row):
                    if i < len(headers) and cell and cell not in (":", "-", ""):
                        lines.append(f"  {headers[i]}: {cell}")
            lines.append("")

    lines.append("-" * 30)

    if len(lines) <= 4:
        text = await p.locator("body").inner_text()
        lines_clean = [l.strip() for l in text.split("\n") if l.strip()]
        start = next((i for i, l in enumerate(lines_clean) if "INFORMACION BASICA" in l.upper()), 0)
        end = next((i for i, l in enumerate(lines_clean) if "FECHA DE IMPRESION" in l.upper()), len(lines_clean))
        relevant = [
            l for l in lines_clean[start:end+1]
            if l.strip() and len(l) < 200
            and "RESPECTO A LAS" not in l.upper()
            and "RESPONSABILIDAD POR" not in l.upper()
            and "ESTA INFORMACION SE" not in l.upper()
            and "SI NECESITA RETIRAR" not in l.upper()
            and "IMPRIMIR" not in l.upper()
            and "CERRAR" not in l.upper()
            and "LA INFORMACION REGISTRADA" not in l.upper()
        ]
        lines = ["*ADRES - CONSULTA AFILIADO*", "-" * 30]
        for line in relevant[:30]:
            lines.append(line)
        lines.append("-" * 30)

    return "\n".join(lines)


def _parse_fallback(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[^;]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "NOMBRE", "APELLIDO", "ESTADO", "EPS", "REGIMEN",
            "AFILIACION", "DOCUMENTO", "CEDULA", "MUNICIPIO",
            "ACTIVO", "SUSPENDIDO", "RETIRADO", "COTIZANTE",
            "BENEFICIARIO", "CONTRIBUTIVO", "SUBSIDIADO",
            "SEXO", "DIRECCION", "TELEFONO", "NACIMIENTO",
        ])
        and "RESPONSABILIDAD" not in l.upper()
        and "RESPECTO A LAS" not in l.upper()
    ][:20]
    if relevant:
        return "*ADRES*\n" + "-" * 30 + "\n" + "\n".join(relevant) + "\n" + "-" * 30
    return "*ADRES*\n" + "-" * 30 + "\nNo se pudo interpretar respuesta.\n" + "-" * 30
