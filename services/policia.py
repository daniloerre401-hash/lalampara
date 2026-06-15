import asyncio
import logging
import re

from .browser_manager import get_page, new_page, browser_ready

logger = logging.getLogger(__name__)

POLICIA_URL = "https://antecedentes.policia.gov.co:7005/WebJudicial/"

DOCUMENT_TYPES_POLICIA = {
    "cedula": "1",
    "ti": "2",
    "ce": "3",
    "pasaporte": "4",
    "nuip": "5",
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(POLICIA_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con Policia Nacional: {e}"

    try:
        await asyncio.sleep(3)

        page_title = await p.title()
        if "Policia" not in page_title and "Policia" not in page_title:
            logger.warning(f"Policia page title unexpected: {page_title}")

        acep_checkbox = await p.locator('input[type="checkbox"]').count()
        if acep_checkbox > 0:
            try:
                await p.locator('input[type="checkbox"]').first.check(timeout=5000)
                await p.evaluate("""() => {
                    const checkbox = document.querySelector('input[type="checkbox"]');
                    if (checkbox) checkbox.checked = true;
                }""")
                await asyncio.sleep(1)

                btns = await p.locator('input[type="submit"], button[type="submit"]').count()
                if btns > 0:
                    await p.locator('input[type="submit"], button[type="submit"]').first.click(timeout=5000)
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"No se pudo aceptar terminos Policia: {e}")

        forms = await p.evaluate("""() => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(f => ({
                action: f.action,
                method: f.method,
                inputs: Array.from(f.querySelectorAll('input, select')).map(i => ({
                    name: i.name,
                    id: i.id,
                    type: i.type,
                    tag: i.tagName
                }))
            }));
        }""")
        logger.info(f"Forms Policia: {forms}")

        doc_type_value = DOCUMENT_TYPES_POLICIA.get(doc_type, "1")

        filled = await p.evaluate(f"""(docTypeValue, docNumber) => {{
            const selects = document.querySelectorAll('select');
            const inputs = document.querySelectorAll('input[type="text"], input[type="number"], input:not([type])');

            selects.forEach(s => {{
                const opts = Array.from(s.options).map(o => o.value.toLowerCase());
                const name = (s.name || '').toLowerCase();
                const id = (s.id || '').toLowerCase();

                if (opts.length >= 2 && (name.includes('tipo') || id.includes('tipo') ||
                    name.includes('doc') || id.includes('doc') || opts.includes('1') || opts.includes('cc'))) {{
                    const vals = Array.from(s.options).map(o => o.value);
                    if (vals.includes(docTypeValue)) {{
                        s.value = docTypeValue;
                    }} else if (vals.length > 1) {{
                        s.selectedIndex = 1;
                    }}
                }}
            }});

            inputs.forEach(i => {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('doc') || id.includes('doc') ||
                    name.includes('numero') || id.includes('numero') ||
                    name.includes('ident') || id.includes('ident') ||
                    name.includes('cedula') || id.includes('cedula') ||
                    name.includes('documento') || id.includes('documento'))) {{
                    i.value = docNumber;
                }}
            }});
            return 'filled';
        }}""", doc_type_value, doc_number)
        logger.info(f"Policia fill result: {filled}")

        result = await p.evaluate(f"""(docNumber) => {{
            const forms = document.forms;
            if (forms.length === 0) return 'ERR:no_forms';

            const form = forms[0];
            const fd = new FormData(form);
            fd.append('__EVENTTARGET', '');
            fd.append('__VIEWSTATE', '');

            return new Promise((resolve) => {{
                const xhr = new XMLHttpRequest();
                xhr.open(form.method || 'POST', form.action || window.location.href, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = () => {{
                    const text = xhr.responseText || '';
                    resolve('OK:' + xhr.status + ':' + text);
                }};
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 30000;
                xhr.send(new URLSearchParams(fd).toString());
            }});
        }}""", doc_number)

        if result.startswith("ERR:"):
            return await _fallback_form(p, doc_number)

        if result.startswith("OK:"):
            parts = result.split(":", 2)
            html = parts[2] if len(parts) > 2 else ""
            return _parse_antecedentes_html(html)

        return str(result)

    except Exception as e:
        logger.exception("Error en consulta Policia")
        return f"Error Policia: {str(e)[:200]}"


async def _fallback_form(p, doc_number: str) -> str:
    try:
        page_text = await p.locator("body").inner_text()

        if any(k in page_text.upper() for k in [
            "NO REGISTRA", "NO TIENE", "SIN ANTECEDENTES",
            "NO PRESENTA", "CERTIFICA QUE", "RESULTADO NEGATIVO",
            "PERSONA NO REGISTRA", "NO SE ENCUENTRAN"
        ]):
            return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
                   "\nResultado: No registra antecedentes judiciales\n" + "-" * 30

        if any(k in page_text.upper() for k in [
            "REGISTRA", "ANTECEDENTES", "TIENE", "POSITIVO",
            "RESULTADO POSITIVO", "SI REGISTRA"
        ]):
            lines = [l.strip() for l in page_text.split("\n") if l.strip()]
            relevant = [
                l for l in lines
                if any(k in l.upper() for k in [
                    "ANTECEDENTE", "DELITO", "FECHA", "JUZGADO",
                    "SENTENCIA", "REGISTRA", "RESULTADO",
                    "AUTORIDAD", "PROCESO", "CONDENA", "NO REGISTRA",
                ])
            ]
            return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
                   "\nATENCION: Posible hallazgo\n\n" + \
                   "\n".join(relevant[:20]) + "\n" + "-" * 30

        cap_text = page_text[:2000]
        return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
               f"\nResultado (texto crudo):\n{cap_text}\n" + "-" * 30

    except Exception as e:
        return f"Error en fallback Policia: {str(e)[:200]}"


def _parse_antecedentes_html(html: str) -> str:
    solo_texto = re.sub(r"<br\s*/?>", "\n", html)
    solo_texto = re.sub(r"<[^>]+>", " ", solo_texto)
    solo_texto = re.sub(r"&[^;]+;", " ", solo_texto)
    solo_texto = re.sub(r"\s+", " ", solo_texto).strip()

    lines = [l.strip() for l in solo_texto.split("\n") if l.strip()]

    if any(k in solo_texto.upper() for k in [
        "NO REGISTRA", "NO TIENE ANTECEDENTES", "SIN ANTECEDENTES",
        "NO PRESENTA ANTECEDENTES"
    ]):
        return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
               "\nResultado: No registra antecedentes judiciales\n" + "-" * 30

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "NOMBRE", "CEDULA", "IDENTIFICACION", "DOCUMENTO",
            "ANTECEDENTE", "DELITO", "FECHA", "JUZGADO",
            "SENTENCIA", "REGISTRA", "RESULTADO", "NO REGISTRA",
            "AUTORIDAD", "PROCESO", "CONDENA",
        ])
    ]
    if relevant:
        return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant[:30]) + "\n" + "-" * 30

    return "*POLICIA NACIONAL - ANTECEDENTES JUDICIALES*\n" + "-" * 30 + \
           f"\nNo se pudo interpretar respuesta.\n\n{lines[:10]}\n" + "-" * 30
