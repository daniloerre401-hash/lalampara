import asyncio
import logging
import re

from .browser_manager import get_page

logger = logging.getLogger(__name__)

PROC_URL = "https://www.procuraduria.gov.co/Pages/certificado-antecedentes.aspx"


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(PROC_URL, timeout=30000)
    except Exception as e:
        return f"Procuraduria error conexion: {e}"

    try:
        await asyncio.sleep(4)

        if "blocked" in (await p.title()).lower():
            return (
                "PROCURADURIA: Sitio bloqueado desde IP no colombiana.\n"
                "Necesitas un proxy/VPN de Colombia para usar este servicio.\n"
                "Consulta manual: https://www.procuraduria.gov.co"
            )

        body = await p.locator("body").inner_text()
        if len(body) < 200 or "no se encuentra disponible" in body.lower():
            return (
                "PROCURADURIA: Sitio no disponible desde esta ubicacion.\n"
                "Necesitas un proxy/VPN de Colombia.\n"
                "Consulta manual: https://www.procuraduria.gov.co"
            )

        dt = doc_type.upper()
        await p.evaluate(f"""(args) => {{
            const dt = args.dt;
            const dn = args.dn;
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            for (let i of inputs) {{
                const name = (i.name || '').toLowerCase();
                const id = (i.id || '').toLowerCase();
                if (!i.value && (name.includes('doc') || id.includes('doc') ||
                    name.includes('ident') || id.includes('ident') ||
                    name.includes('cedula') || id.includes('cedula') ||
                    name.includes('numero') || id.includes('numero'))) {{
                    i.value = dn; break;
                }}
            }}
            const selects = document.querySelectorAll('select');
            for (let s of selects) {{
                const opts = Array.from(s.options);
                let found = opts.find(o =>
                    o.value.toUpperCase().includes(dt) ||
                    o.text.toUpperCase().includes(dt)
                );
                if (found) {{ s.value = found.value; break; }}
            }}
        }}""", {"dt": dt, "dn": doc_number})

        await p.evaluate("""() => {
            const btns = document.querySelectorAll('button, input[type=submit], a.btn, a[role=button]');
            for (let b of btns) {
                if (/consultar|buscar|generar|enviar/i.test(b.innerText || b.value || b.textContent || '')) {
                    b.click(); break;
                }
            }
        }""")
        await asyncio.sleep(5)

        text = await p.locator("body").inner_text()
        return _parse(text, doc_number)

    except Exception as e:
        logger.exception("Procuraduria error")
        return f"Procuraduria error: {str(e)[:200]}"


def _parse(text: str, query: str = "") -> str:
    t = text.upper()

    if any(k in t for k in [
        "NO REGISTRA", "NO TIENE", "NO PRESENTA", "CERTIFICA QUE NO",
        "ANTECEDENTES NEGATIVOS", "NO APARECE", "SIN ANTECEDENTES",
        "NO SE ENCUENTRAN",
    ]):
        return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
               "\nNo registra antecedentes disciplinarios\n" + "-" * 30

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    keywords = [
        "SANCION", "INHABILIDAD", "FECHA", "RADICADO",
        "ENTIDAD", "CARGO", "FALTA", "REGISTRA", "NO REGISTRA",
        "DISCIPLINARIO", "ANTECEDENTE", "NOMBRE", "CEDULA",
    ]
    relevant = [l for l in lines if any(k in l.upper() for k in keywords)][:20]
    if relevant:
        return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
               "\n" + "\n".join(relevant) + "\n" + "-" * 30

    return "*PROCURADURIA - ANTECEDENTES DISCIPLINARIOS*\n" + "-" * 30 + \
           "\nNo se pudo interpretar. Consulte en: procuraduria.gov.co\n" + "-" * 30
