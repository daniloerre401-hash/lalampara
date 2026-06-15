import asyncio
import logging
import re

from .browser_manager import get_page
from . import captcha

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
        return f"Error al abrir navegador ADRES: {e}"

    try:
        if await p.locator("#tipoDoc").count() == 0:
            await p.goto(ADRES_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            if await p.locator("#tipoDoc").count() == 0:
                return "ADRES: formulario no encontrado (sitio caido o cambio)"

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
                logger.info(f"ADRES resultado: {result_url}")

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
                    if (key && val && val !== ':') {
                        data[key] = val;
                    }
                }
            });
        });
        return data;
    }""")

    if rows and len(rows) > 2:
        return _format(rows)

    text = await p.locator("body").inner_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    start = next((i for i, l in enumerate(lines) if "INFORMACION BASICA" in l.upper()), 0)
    end = next((i for i, l in enumerate(lines) if "FECHA DE IMPRESION" in l.upper()), len(lines))
    data = lines[start:end + 1] if end < len(lines) else lines[start:]
    return _format_list(data)


def _format(data: dict) -> str:
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
        "SEXO", "DIRECCION", "TELEFONO",
    ]
    lines = ["*ADRES - CONSULTA AFILIADO*", "-" * 30]
    seen = set()
    for key in order:
        norm = key.upper().strip()
        if norm in data:
            lines.append(f"{norm.title()}: {data[norm]}")
            seen.add(norm)
    for k, v in data.items():
        if k not in seen:
            lines.append(f"{k.title()}: {v}")
            seen.add(k)
    lines.append("-" * 30)
    return "\n".join(lines)


def _format_list(data: list) -> str:
    cleaned = []
    for line in data:
        line = line.strip()
        if not line or line in (":", "-", ""):
            continue
        if any(s in line.upper() for s in ["FECHA DE IMPRESION", "PAGINA", "PAGE", "IMPRESION"]):
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


def _parse_fallback(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[^;]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    keywords = [
        "NOMBRE", "APELLIDO", "ESTADO", "EPS", "REGIMEN",
        "AFILIACION", "DOCUMENTO", "CEDULA", "MUNICIPIO",
        "ACTIVO", "SUSPENDIDO", "RETIRADO", "COTIZANTE",
        "BENEFICIARIO", "CONTRIBUTIVO", "SUBSIDIADO",
        "SEXO", "DIRECCION", "TELEFONO", "NACIMIENTO",
    ]
    relevant = [l for l in lines if any(k in l.upper() for k in keywords)]
    if relevant:
        return _format_list(relevant)

    words = text.split()
    chunks = [" ".join(words[i:i + 20]) for i in range(0, len(words), 20)]
    return "*ADRES*\n" + "-" * 30 + "\n" + "\n".join(chunks[:20]) + "\n" + "-" * 30
