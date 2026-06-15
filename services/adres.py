import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

ADRES_URL = "https://aplicaciones.adres.gov.co/BDUA_Internet/Pages/ConsultarAfiliadoWeb_2.aspx"

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


async def consultar(doc_type_value: str, doc_number: str) -> str:
    try:
        p = await get_page(ADRES_URL)
    except Exception as e:
        return f"Error al abrir navegador: {e}. Usa /start"

    try:
        if await p.locator("#tipoDoc").count() == 0:
            await p.goto(ADRES_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            if await p.locator("#tipoDoc").count() == 0:
                return "Formulario ADRES no encontrado. El sitio puede estar caido o cambio."

        await p.evaluate(
            f"document.getElementById('tipoDoc').value = '{doc_type_value}';"
        )
        await p.evaluate(
            f"document.getElementById('txtNumDoc').value = '{doc_number}';"
        )

        result_data = await p.evaluate("""() => {
            const btn = document.getElementById('btnConsultar');
            const form = document.forms[0];
            if (!btn || !form) return 'ERR:no_form_btn';

            const fd = new FormData(form);
            fd.append(btn.name, btn.value);

            return new Promise((resolve) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', form.action, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = () => {
                    resolve('OK:' + xhr.status + ':' + (xhr.responseText || ''));
                };
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 25000;
                xhr.send(new URLSearchParams(fd).toString());
            });
        }""")

        if result_data.startswith("ERR:"):
            return f"Error en consulta ADRES: {result_data}"

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
                logger.info(f"Abriendo resultado ADRES: {result_url}")

                try:
                    await p.goto(result_url, wait_until="load", timeout=60000)
                except Exception:
                    try:
                        await p.goto(result_url, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                await asyncio.sleep(3)
                return await _parse_result_page(p)

            return _parse_html_fallback(html)

        return result_data

    except Exception as e:
        logger.exception("Error en consulta ADRES")
        estr = str(e)
        if "closed" in estr.lower() or "detached" in estr.lower():
            return "La ventana del navegador se cerro. Usa /start para reabrirla."
        return f"Error: {estr[:200]}"


async def _parse_result_page(p) -> str:
    rows = await p.evaluate("""() => {
        const tables = document.querySelectorAll('table');
        const data = {};
        tables.forEach(table => {
            const trs = table.querySelectorAll('tr');
            trs.forEach(tr => {
                const th = tr.querySelector('th');
                const td = tr.querySelector('td');
                if (th && td) {
                    let key = th.innerText.trim().replace(/[\\s:]+/g, ' ').toUpperCase().trim();
                    let val = td.innerText.trim().replace(/\\s+/g, ' ');
                    if (key && val && val !== ':' && !key.includes('nbsp')) {
                        data[key] = val;
                    }
                }
            });
        });
        return data;
    }""")

    if rows and len(rows) > 2:
        return _format_result_dict(rows)

    text = await p.locator("body").inner_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    start = next((i for i, l in enumerate(lines) if "INFORMACION BASICA" in l.upper()), 0)
    end = next((i for i, l in enumerate(lines) if "FECHA DE IMPRESION" in l.upper()), len(lines))
    data = lines[start:end + 1] if end < len(lines) else lines[start:]
    return _format_result_list(data)


def _format_result_dict(data: dict) -> str:
    label_map = {
        "NOMBRE": "Nombre",
        "PRIMER APELLIDO": "Apellido",
        "SEGUNDO APELLIDO": "Apellido",
        "APELLIDOS": "Apellidos",
        "NOMBRES": "Nombres",
        "TIPO DOCUMENTO": "Tipo Doc",
        "NUMERO DOCUMENTO": "Numero Doc",
        "DOCUMENTO": "Documento",
    }
    order = [
        "TIPO DOCUMENTO", "NUMERO DOCUMENTO", "DOCUMENTO",
        "PRIMER APELLIDO", "SEGUNDO APELLIDO", "APELLIDOS",
        "NOMBRES", "NOMBRE",
        "ESTADO", "ESTADO DE AFILIACION",
        "EPS", "NOMBRE EPS",
        "REGIMEN",
        "FECHA DE AFILIACION", "FECHA DE NACIMIENTO",
        "MUNICIPIO", "DEPARTAMENTO",
        "TIPO DE AFILIADO", "COTIZANTE", "BENEFICIARIO",
        "SEXO",
        "DIRECCION", "TELEFONO",
    ]

    lines = ["*ADRES - CONSULTA AFILIADO*", "-" * 30]
    seen = set()
    for key in order:
        norm = key.upper().strip()
        if norm in data:
            label = label_map.get(norm, norm.title())
            lines.append(f"{label}: {data[norm]}")
            seen.add(norm)

    for key, val in data.items():
        if key not in seen:
            label = label_map.get(key, key.title())
            lines.append(f"{label}: {val}")
            seen.add(key)

    lines.append("-" * 30)
    return "\n".join(lines)


def _format_result_list(data: list) -> str:
    cleaned = []
    for line in data:
        line = line.strip()
        if not line or line in (":", "-", ""):
            continue
        if any(skip in line.upper() for skip in [
            "FECHA DE IMPRESION", "FECHA DE IMPRESION",
            "PAGINA", "PAGE", "IMPRESION", "IMPRESION"
        ]):
            continue
        cleaned.append(line)

    formatted = ["*ADRES - CONSULTA AFILIADO*", "-" * 30]
    for line in cleaned[:40]:
        if ":" in line:
            parts = line.split(":", 1)
            formatted.append(f"{parts[0].strip()}: {parts[1].strip()}")
        else:
            formatted.append(line)
    formatted.append("-" * 30)
    return "\n".join(formatted)


def _parse_html_fallback(html: str) -> str:
    solo_texto = re.sub(r"<br\s*/?>", "\n", html)
    solo_texto = re.sub(r"<[^>]+>", " ", solo_texto)
    solo_texto = re.sub(r"&[^;]+;", " ", solo_texto)
    solo_texto = re.sub(r"\s+", " ", solo_texto).strip()

    lines = [l.strip() for l in solo_texto.split("\n") if l.strip()]
    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "NOMBRE", "APELLIDO", "ESTADO", "EPS", "REGIMEN",
            "AFILIACION", "AFILIADO", "DOCUMENTO", "CEDULA",
            "IDENTIFICACION", "MUNICIPIO", "DEPARTAMENTO",
            "ACTIVO", "SUSPENDIDO", "RETIRADO", "FECHA",
            "COTIZANTE", "BENEFICIARIO", "CONTRIBUTIVO", "SUBSIDIADO",
            "SEXO", "DIRECCION", "TELEFONO", "NACIMIENTO",
        ])
    ]
    if relevant:
        return _format_result_list(relevant)

    words = solo_texto.split()
    chunks = []
    for i in range(0, len(words), 20):
        chunks.append(" ".join(words[i:i + 20]))
    return "\n".join(chunks[:30])
