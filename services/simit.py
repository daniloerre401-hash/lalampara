import asyncio
import logging
import re
import json

from .browser_manager import get_page, new_page

logger = logging.getLogger(__name__)

SIMIT_SPA_URL = "https://www.fcm.org.co/simit/#/consulta-public"
SIMIT_API_BASE = "https://consultasimit.fcm.org.co/simit/microservices/estado-cuenta-simit/estadocuenta"

SIMIT_DOC_TYPES = {
    "cc": 1, "cedula": 1,
    "ce": 3, "extranjeria": 3,
    "nit": 4,
    "ti": 6, "tarjeta": 6,
    "cd": 7, "diplomatico": 7,
    "pa": 2, "pasaporte": 2,
}


async def consultar(doc_type: str, doc_number: str) -> str:
    try:
        p = await new_page()
        await p.goto(SIMIT_SPA_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return f"SIMIT error conexion: {e}"

    try:
        await asyncio.sleep(6)

        doc_type_id = SIMIT_DOC_TYPES.get(doc_type, 1)

        sitekey = await _get_sitekey(p)
        if not sitekey:
            return (
                "SIMIT: no se encontro reCAPTCHA en la pagina.\n"
                "Link manual: https://www.fcm.org.co/simit/"
            )

        token = await cap.solve_recaptcha_v2(p, sitekey)
        if not token:
            return (
                "SIMIT: reCAPTCHA no resuelto.\n"
                "Verifica CAPTCHA_API_KEY en .env (2captcha.com)\n"
                "Link manual: https://www.fcm.org.co/simit/"
            )

        result = await p.evaluate(f"""(apiBase, docTypeId, docNumber, recaptchaToken) => {{
            return new Promise((resolve) => {{
                const xhr = new XMLHttpRequest();
                xhr.open('POST', apiBase + '/consulta', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onload = () => {{
                    resolve(JSON.stringify({{
                        status: xhr.status,
                        body: xhr.responseText ? xhr.responseText.slice(0, 10000) : ''
                    }}));
                }};
                xhr.onerror = () => resolve('ERR:xhr_error');
                xhr.ontimeout = () => resolve('ERR:timeout');
                xhr.timeout = 25000;
                xhr.send(JSON.stringify({{
                    infoPersona: {{
                        idTipoDocumento: docTypeId,
                        numeroDocumento: docNumber
                    }},
                    reCaptchaDTO: {{
                        response: recaptchaToken,
                        consumidor: 'DESKTOP'
                    }},
                    numDocPlaca: docNumber
                }}));
            }});
        }}""", SIMIT_API_BASE, doc_type_id, doc_number, token)

        if result.startswith("ERR:"):
            return f"SIMIT error: {result}"

        try:
            data = json.loads(result)
            status = data.get("status", 0)
            body = data.get("body", "")
        except Exception:
            return f"SIMIT respuesta invalida: {result[:500]}"

        if status != 200:
            return f"SIMIT respondio HTTP {status}"

        return _parse_body(body, doc_number)

    except Exception as e:
        logger.exception("SIMIT error")
        return f"SIMIT error: {str(e)[:200]}"


async def _get_sitekey(p) -> str | None:
    sitekey = await p.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe[src*="recaptcha"]');
        for (let f of iframes) {
            const m = f.src.match(/[?&]k=([^&]+)/);
            if (m) return m[1];
        }
        const html = document.documentElement.innerHTML;
        const m = html.match(/6L[a-zA-Z0-9_-]{30,}/);
        if (m) return m[0];
        return null;
    }""")
    return sitekey


def _parse_body(text: str, query: str = "") -> str:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _parse_dict(data, query)
        if isinstance(data, list):
            return _parse_list(data, query)
    except (json.JSONDecodeError, TypeError):
        pass

    t = text.upper()
    if any(k in t for k in [
        "NO REGISTRA", "NO TIENE MULTAS", "SIN MULTAS",
        "PAZ Y SALVO", "NO ADEUDA", "NO PRESENTA",
    ]):
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\nPaz y salvo: No registra multas de transito\n" + "-" * 30

    if any(k in t for k in ["COMPARENDO", "MULTA", "INFRACCION"]):
        return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
               "\n" + text[:2000] + "\n" + "-" * 30

    return "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 30 + \
           "\nConsulta manual: https://www.fcm.org.co/simit/\n" + "-" * 30


def _parse_dict(data: dict, query: str = "") -> str:
    multas = data.get("multas", [])
    acuerdos = data.get("acuerdosPago", [])
    total = data.get("totalGeneral", 0)
    paz_salvo = data.get("pazSalvo", False)

    result = "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 35 + "\n"

    if paz_salvo and not multas:
        result += "Resultado: PAZ Y SALVO - No registra multas\n"
        result += "-" * 35
        return result

    if not multas and not acuerdos:
        result += "No se encontraron multas ni acuerdos de pago.\n"
        result += "-" * 35
        return result

    if total:
        result += f"Total deuda: ${total:,.0f} COP\n\n"

    for i, m in enumerate(multas[:20], 1):
        result += f"*Comparendo {i}:*\n"
        infra = m.get("infractor", {})
        result += f"  Infractor: {infra.get('nombre', '')} {infra.get('apellido', '')}\n"
        result += f"  Documento: {infra.get('tipoDocumento', '')} {infra.get('numeroDocumento', '')}\n"
        result += f"  Placa: {m.get('placa', 'N/A')}\n"
        result += f"  Valor: ${m.get('valor', 0):,.0f} COP\n"

        infracciones = m.get("infracciones", [])
        for inf in infracciones[:3]:
            result += f"  - {inf.get('codigoInfraccion', '')}: {inf.get('descripcionInfraccion', '')[:80]}\n"
            result += f"    Valor: ${inf.get('valorInfraccion', 0):,.0f} COP\n"
        result += "\n"

    if acuerdos:
        result += f"*Acuerdos de pago ({len(acuerdos)}):*\n"
        for a in acuerdos[:5]:
            result += f"  Cuotas pendientes: {a.get('cuotasPendientes', 'N/A')}\n"

    result += "-" * 35
    return result


def _parse_list(data: list, query: str = "") -> str:
    result = "*SIMIT - MULTAS DE TRANSITO*\n" + "-" * 35 + "\n"
    if not data:
        result += "No se encontraron resultados.\n"
    else:
        result += f"Se encontraron {len(data)} registros.\n"
        for i, item in enumerate(data[:10], 1):
            result += f"\n*Registro {i}:*\n"
            if isinstance(item, dict):
                for k, v in item.items():
                    result += f"  {k}: {v}\n"
            else:
                result += f"  {item}\n"
    result += "-" * 35
    return result
