import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

PROCURADURIA_URL = "https://www.procuraduria.gov.co/Pages/GenerarCerti.aspx"

DOCUMENT_TYPES_PROC = {
    "cedula": "CC",
    "ti": "TI",
    "ce": "CE",
    "pasaporte": "PA",
    "nit": "NI",
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(PROCURADURIA_URL, timeout=90000)
    except Exception as e:
        logger.warning(f"Procuraduria URL1 fallo: {e}")
        try:
            p = await get_page(
                "https://www.procuraduria.gov.co/Pages/consulta-de-antecedentes.aspx",
                timeout=90000,
            )
        except Exception as e2:
            return f"Error al conectar con Procuraduria: {e2}"

    try:
        await asyncio.sleep(4)

        doc_type_value = DOCUMENT_TYPES_PROC.get(doc_type, "CC")

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
            return _parse_procuraduria_fallback(page_text)

        if result.startswith("OK:"):
            parts = result.split(":", 2)
            html = parts[2] if len(parts) > 2 else ""
            return _parse_procuraduria_result(html)

        return str(result)

    except Exception as e:
        logger.exception("Error en consulta Procuraduria")
        return f"Error Procuraduria: {str(e)[:200]}"


def _parse_procuraduria_fallback(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if any(k in text.upper() for k in [
        "NO REGISTRA", "NO TIENE ANTECEDENTES", "NO PRESENTA",
        "CERTIFICA QUE NO", "ANTECEDENTES NEGATIVOS",
        "NO SE ENCUENTRAN SANCIONES", "NO APARECE",
    ]):
        return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
               "\nCertificacion: No registra antecedentes disciplinarios\n" + "-" * 30

    if any(k in text.upper() for k in [
        "REGISTRA", "SANCION", "INHABILIDAD", "DISCIPLINARIO",
        "FALTA", "ANTECEDENTES POSITIVOS",
    ]):
        relevant = [
            l for l in lines
            if any(k in l.upper() for k in [
                "SANCION", "INHABILIDAD", "FECHA", "RADICADO",
                "ENTIDAD", "CARGO", "FALTA", "REGISTRA",
                "DISCIPLINARIO", "ANTECEDENTE", "NOMBRE",
            ])
        ]
        return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
               "\nATENCION: Posibles antecedentes\n\n" + \
               "\n".join(relevant[:20]) + "\n" + "-" * 30

    return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar. Respuesta:\n{lines[:10]}\n" + "-" * 30


def _parse_procuraduria_result(html: str) -> str:
    solo_texto = re.sub(r"<br\s*/?>", "\n", html)
    solo_texto = re.sub(r"<[^>]+>", " ", solo_texto)
    solo_texto = re.sub(r"&[^;]+;", " ", solo_texto)
    solo_texto = re.sub(r"\s+", " ", solo_texto).strip()

    return _parse_procuraduria_fallback(solo_texto)
