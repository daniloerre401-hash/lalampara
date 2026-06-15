import asyncio
import logging
import re

from .browser_manager import get_page
from . import captcha

logger = logging.getLogger(__name__)

SISBEN_URL = "https://reportes.sisben.gov.co/dnp_sisbenconsulta"

SISBEN_DOC_TYPES = {
    "rc": "1", "registro_civil": "1", "registrocivil": "1",
    "ti": "2", "tarjeta_identidad": "2",
    "cc": "3", "cedula": "3", "cedula_ciudadania": "3",
    "ce": "4", "cedula_extranjeria": "4", "extranjeria": "4",
    "dni": "5",
    "pasaporte": "6", "dni_pasaporte": "6",
    "salvoconducto": "7",
    "pep": "8", "permiso_especial": "8",
    "ppt": "9", "proteccion_temporal": "9",
}

SISBEN_LABELS = {
    "1": "Registro Civil", "2": "Tarjeta de Identidad",
    "3": "Cedula de Ciudadania", "4": "Cedula de Extranjeria",
    "5": "DNI (Pais de origen)", "6": "DNI (Pasaporte)",
    "7": "Salvoconducto", "8": "Permiso Especial de Permanencia",
    "9": "Permiso por Proteccion Temporal",
}

SISBEN_GROUPS = {
    "A": "POBREZA EXTREMA",
    "B": "POBREZA MODERADA",
    "C": "VULNERABLE",
    "D": "NO POBRE, NO VULNERABLE",
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await get_page(SISBEN_URL, timeout=45000)
    except Exception as e:
        return f"Error al conectar con SISBEN: {e}"

    try:
        await p.goto(SISBEN_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        tipo_id = await p.locator("#TipoID").count()
        if tipo_id == 0:
            return "SISBEN: formulario no encontrado. El sitio puede haber cambiado."

        doc_type_value = SISBEN_DOC_TYPES.get(doc_type, "3")

        token = await p.evaluate("""() => {
            const inp = document.querySelector('input[name=__RequestVerificationToken]');
            return inp ? inp.value : '';
        }""")

        await p.evaluate(f"""() => {{
            document.getElementById('TipoID').value = '{doc_type_value}';
            document.getElementById('documento').value = '{doc_number}';
        }}""")

        result = await p.evaluate(f"""(token) => {{
            const form = document.forms[0];
            const fd = new FormData(form);
            fd.set('TipoID', document.getElementById('TipoID').value);
            fd.set('documento', '{doc_number}');
            fd.set('__RequestVerificationToken', token);

            return new Promise((resolve) => {{
                const xhr = new XMLHttpRequest();
                xhr.open('POST', form.action, true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.setRequestHeader('RequestVerificationToken', token);
                xhr.onload = () => {{
                    resolve('OK:' + xhr.status + ':' + (xhr.responseText || ''));
                }};
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 25000;
                xhr.send(new URLSearchParams(fd).toString());
            }});
        }}""", token)

        if result.startswith("ERR:"):
            return f"SISBEN error: {result.replace('ERR:', '')}"

        if result.startswith("OK:"):
            parts = result.split(":", 2)
            html = parts[2] if len(parts) > 2 else ""
            return _parse(html, doc_number)

        return str(result)

    except Exception as e:
        logger.exception("SISBEN error")
        return f"SISBEN error: {str(e)[:200]}"


def _parse(html: str, doc_number: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text_upper = text.upper()

    if any(k in text_upper for k in [
        "NO SE ENCUENTRA", "NO SE ENCONTRO", "NO REGISTRA",
        "SIN RESULTADOS", "NO POSEE", "DOCUMENTO NO VALIDO",
        "NO ESTA REGISTRADO", "NO CUENTA CON",
    ]):
        label = SISBEN_DOC_TYPES.get(doc_number, doc_number)
        return "*SISBEN IV - RESULTADO*\n" + "-" * 30 + \
               "\nLa persona NO se encuentra registrada en SISBEN IV\n" + "-" * 30

    grupo = None
    m = re.search(r'(?:grupo|clasificacion)[:\s]*([ABCD])\d*', text_upper)
    if m:
        grupo = m.group(1)

    subgrupo = None
    m2 = re.search(r'([ABCD]\d{1,2})', text_upper)
    if m2:
        subgrupo = m2.group(1)

    nombre = None
    m3 = re.search(r'(?:nombre|nombres)[:\s]+([A-Za-z\u00C0-\u024F\s]+?)(?:\s{2,}|$)', text, re.IGNORECASE)
    if m3:
        nombre = m3.group(1).strip()

    puntaje = None
    m4 = re.search(r'(?:puntaje|puntuacion)[:\s]*(\d+[\.,]\d+)', text_upper)
    if m4:
        puntaje = m4.group(1)

    result = "*SISBEN IV - CLASIFICACION*\n" + "-" * 30
    if subgrupo:
        result += f"\nGrupo: {subgrupo}"
        if grupo:
            categoria = SISBEN_GROUPS.get(grupo, "")
            if categoria:
                result += f" ({categoria})"
    if nombre:
        result += f"\nNombre: {nombre}"
    if puntaje:
        result += f"\nPuntaje: {puntaje}"
    result += "\n" + "-" * 30

    if not subgrupo:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        result += "\n" + "\n".join(lines[:12])

    return result
