import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

SIMIT_URL = "https://fase2.simit.org.co/Simit/index.html"

DOCUMENT_TYPES_SIMIT = {
    "cedula": "CC",
    "ti": "TI",
    "ce": "CE",
    "nit": "NI",
    "pasaporte": "PA",
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(SIMIT_URL, timeout=90000)
    except Exception as e:
        try:
            p = await get_page("https://www.simit.org.co/", timeout=90000)
        except Exception as e2:
            return f"Error al conectar con SIMIT: {e2}"

    try:
        await asyncio.sleep(5)

        doc_type_value = DOCUMENT_TYPES_SIMIT.get(doc_type, "CC")

        await p.evaluate(f"""(docTypeValue, docNumber) => {{
            const selects = document.querySelectorAll('select');
            selects.forEach(s => {{
                const opts = Array.from(s.options);
                const matching = opts.find(o =>
                    o.value.toUpperCase().includes(docTypeValue.toUpperCase()) ||
                    o.text.toUpperCase().includes(docTypeValue.toUpperCase())
                );
                if (matching) s.value = matching.value;
            }});
            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('doc') || id.includes('doc') ||
                    name.includes('numero') || id.includes('numero') ||
                    name.includes('ident') || id.includes('ident') ||
                    name.includes('cedula') || id.includes('cedula'))) {{
                    i.value = docNumber;
                }}
            }});
        }}""", doc_type_value, doc_number)

        result = await p.evaluate("""() => {
            const form = document.forms[0];
            if (!form) return 'ERR:no_form';

            const fd = new FormData(form);

            return new Promise((resolve) => {
                const xhr = new XMLHttpRequest();
                xhr.open(form.method || 'POST', form.action || window.location.href, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = () => {
                    const text = xhr.responseText || '';
                    resolve('OK:' + xhr.status + ':' + text);
                };
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 30000;
                xhr.send(new URLSearchParams(fd).toString());
            });
        }""")

        if result.startswith("ERR:"):
            page_text = await p.locator("body").inner_text()
            return _parse_simit_fallback(page_text)

        if result.startswith("OK:"):
            parts = result.split(":", 2)
            html = parts[2] if len(parts) > 2 else ""
            return _parse_simit_result(html)

        return str(result)

    except Exception as e:
        logger.exception("Error en consulta SIMIT")
        return f"Error SIMIT: {str(e)[:200]}"


def _parse_simit_result(html: str) -> str:
    solo_texto = re.sub(r"<br\s*/?>", "\n", html)
    solo_texto = re.sub(r"<[^>]+>", " ", solo_texto)
    solo_texto = re.sub(r"&[^;]+;", " ", solo_texto)
    solo_texto = re.sub(r"\s+", " ", solo_texto).strip()

    return _parse_simit_fallback(solo_texto)


def _parse_simit_fallback(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text.upper() for k in [
        "NO REGISTRA", "NO TIENE MULTAS", "SIN MULTAS",
        "NO PRESENTA", "PAZ Y SALVO", "NO SE ENCUENTRAN",
        "CERO MULTAS", "NO ADEUDA",
    ]):
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\nResultado: No registra multas de transito (paz y salvo)\n" + "-" * 30

    multas = []
    current = {}
    for line in lines:
        upper = line.upper()
        if "COMPARENDO" in upper or "ORDEN" in upper or "MULTA" in upper:
            if current and (current.get("comparendo") or current.get("monto")):
                multas.append(current)
            current = {"comparendo": line}
        elif current:
            if "FECHA" in upper or "INFRACCION" in upper:
                current["fecha"] = line
            elif "VALOR" in upper or "MONTO" in upper or "SALDO" in upper:
                current["monto"] = line
            elif "PLACA" in upper:
                current["placa"] = line
            elif "ESTADO" in upper:
                current["estado"] = line
            elif "ORGANISMO" in upper or "ENTIDAD" in upper:
                current["organismo"] = line
    if current and (current.get("comparendo") or current.get("monto")):
        multas.append(current)

    if multas:
        result = f"*SIMIT - MULTAS DE TRANSITO* ({len(multas)} encontradas)\n" + "-" * 30
        for i, m in enumerate(multas[:15], 1):
            result += f"\n*Multa {i}:*"
            for key, val in m.items():
                clean_val = val.split(":", 1)[-1].strip() if ":" in val else val
                result += f"\n  {key.title()}: {clean_val}"
        result += "\n" + "-" * 30
        return result

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "COMPARENDO", "MULTA", "VALOR", "MONTO", "SALDO",
            "FECHA", "PLACA", "ESTADO", "INFRACCION",
            "ORGANISMO", "PAZ Y SALVO", "DEUDA", "TOTAL",
            "NO REGISTRA", "SIN MULTAS",
        ])
    ][:25]

    if relevant:
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar resultado.\n\n{lines[:10]}\n" + "-" * 30
