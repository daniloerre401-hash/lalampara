import asyncio
import logging
import re

from .browser_manager import get_page, browser_ready

logger = logging.getLogger(__name__)

SISBEN_URL = "https://www.sisben.gov.co/Paginas/consulta-tu-grupo.html"

DOCUMENT_TYPES_SISBEN = {
    "cedula": "CC",
    "ti": "TI",
    "ce": "CE",
    "rc": "RC",
    "pasaporte": "PA",
    "as": "AS",
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(SISBEN_URL, timeout=90000)
    except Exception as e:
        return f"Error al conectar con SISBEN: {e}"

    try:
        await asyncio.sleep(4)

        page_title = await p.title()

        iframes = await p.locator("iframe").count()
        if iframes > 0:
            logger.info(f"SISBEN: {iframes} iframes encontrados")
            for i in range(iframes):
                try:
                    frame = p.frame_locator("iframe").nth(i)
                    frame_url = await frame.locator("body").evaluate("() => window.location.href")
                    logger.info(f"SISBEN iframe {i}: {frame_url}")
                except Exception:
                    pass

        forms = await p.evaluate("""() => {
            const allForms = document.querySelectorAll('form');
            const result = [];
            allForms.forEach(f => {
                result.push({
                    action: f.action,
                    id: f.id,
                    inputs: Array.from(f.querySelectorAll('input, select')).map(i => ({
                        name: i.name, id: i.id, type: i.type, tag: i.tagName,
                        placeholder: i.placeholder || ''
                    }))
                });
            });
            return result;
        }""")
        logger.info(f"SISBEN forms: {forms}")

        doc_type_value = DOCUMENT_TYPES_SISBEN.get(doc_type, "CC")

        filled = await p.evaluate(f"""(docTypeValue, docNumber) => {{
            const selects = document.querySelectorAll('select');
            const inputs = document.querySelectorAll('input[type="text"], input[type="number"], input:not([type])');

            selects.forEach(s => {{
                const opts = Array.from(s.options);
                const matching = opts.find(o =>
                    o.value.toUpperCase().includes(docTypeValue.toUpperCase()) ||
                    o.text.toUpperCase().includes(docTypeValue.toUpperCase())
                );
                if (matching) {{
                    s.value = matching.value;
                }}
            }});

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
            return 'filled';
        }}""", doc_type_value, doc_number)
        logger.info(f"SISBEN fill result: {filled}")

        submit_btns = await p.evaluate("""() => {
            const btns = document.querySelectorAll('input[type="submit"], button[type="submit"], button, a.btn');
            return Array.from(btns).map(b => ({ id: b.id, text: b.innerText?.slice(0, 30), type: b.type }));
        }""")

        clicked = False
        for btn_info in submit_btns:
            btn_text = (btn_info.get("text") or "").upper()
            if any(k in btn_text for k in ["CONSULTAR", "BUSCAR", "ENVIAR", "ACEPTAR", "CONTINUAR"]):
                try:
                    if btn_info.get("id"):
                        await p.locator(f"#{btn_info['id']}").click(timeout=5000)
                        clicked = True
                        break
                except Exception:
                    pass

        if not clicked:
            try:
                await p.evaluate("""() => {
                    const form = document.forms[0];
                    if (form) {
                        const fd = new FormData(form);
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', form.action || window.location.href, true);
                        xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                        xhr.send(new URLSearchParams(fd).toString());
                    }
                }""")
            except Exception as e:
                logger.warning(f"SISBEN submit error: {e}")

        await asyncio.sleep(5)

        result_html = await p.content()
        result_text = await p.locator("body").inner_text()

        return _parse_sisben_result(result_text, result_html)

    except Exception as e:
        logger.exception("Error en consulta SISBEN")
        return f"Error SISBEN: {str(e)[:200]}"


def _parse_sisben_result(text: str, html: str = "") -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    grupo = None
    subgrupo = None
    nombre = None
    puntaje = None

    for line in lines:
        upper = line.upper()
        if "GRUPO:" in upper or "GRUPO SISBEN" in upper or "CLASIFICACION" in upper:
            parts = line.replace(":", " ").split()
            for i, p in enumerate(parts):
                p_upper = p.upper()
                if p_upper in ("A", "B", "C", "D") and len(p) == 1:
                    if i + 1 < len(parts):
                        grupo = f"{p}{parts[i + 1]}"
                    else:
                        grupo = p
                    break
                if re.match(r"^[ABCD]\d", p_upper):
                    grupo = p_upper
                    break
        if "PUNTAJE" in upper or "PUNTUACION" in upper:
            puntaje_match = re.search(r"(\d+[\.,]\d+)", line)
            if puntaje_match:
                puntaje = puntaje_match.group(1)
        if "NOMBRE" in upper:
            parts = line.split(":", 1)
            if len(parts) > 1:
                nombre = parts[1].strip()

    if grupo:
        result = "*SISBEN IV - CLASIFICACION*\n" + "-" * 30
        result += f"\nGrupo: {grupo}"
        if nombre:
            result += f"\nNombre: {nombre}"
        if puntaje:
            result += f"\nPuntaje: {puntaje}"

        grupo_letra = grupo[0] if grupo else ""
        if grupo_letra == "A":
            result += "\n\nCategoria: POBREZA EXTREMA"
        elif grupo_letra == "B":
            result += "\n\nCategoria: POBREZA MODERADA"
        elif grupo_letra == "C":
            result += "\n\nCategoria: VULNERABLE"
        elif grupo_letra == "D":
            result += "\n\nCategoria: NO POBRE, NO VULNERABLE"

        result += "\n" + "-" * 30
        return result

    relevant = [
        l for l in lines
        if any(k in l.upper() for k in [
            "GRUPO", "SISBEN", "PUNTAJE", "CLASIFICACION",
            "NOMBRE", "DOCUMENTO", "IDENTIFICACION",
            "POBREZA", "VULNERABLE", "SUBSIDIO",
            "FECHA", "ENCUESTA", "METODOLOGIA",
            "NO SE ENCUENTRA", "NO REGISTRA",
        ])
    ]
    if relevant:
        return "*SISBEN IV - RESULTADO*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant[:25]) + "\n" + "-" * 30

    return "*SISBEN IV - RESULTADO*\n" + "-" * 30 + \
           f"\nNo se pudo extraer grupo. Respuesta:\n{lines[:15]}\n" + "-" * 30
