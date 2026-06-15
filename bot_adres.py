import os
import logging
import asyncio

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from services import adres, policia, sisben, rama_judicial, procuraduria
from services import simit, runt, rues
from services.browser_manager import kill_browser, get_page, browser_ready

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADRES_URL = adres.ADRES_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP = (
    "BOT DE CONSULTAS COLOMBIA\n"
    "===============================\n"
    "Salud:\n"
    "  /adres <tipo> <doc> — Afiliacion EPS\n"
    "  /sisben <tipo> <doc> — Grupo Sisben IV\n\n"
    "Antecedentes:\n"
    "  /policia <tipo> <doc> — Antecedentes judiciales\n"
    "  /procuraduria <tipo> <doc> — Antecedentes disciplinarios\n\n"
    "Judicial:\n"
    "  /rama_doc <doc> — Procesos x documento\n"
    "  /rama_nombre <nombres> [apellidos]\n"
    "  /rama_proc <radicado>\n\n"
    "Transito:\n"
    "  /simit <tipo> <doc> — Multas de transito\n"
    "  /runt_placa <ABC123> — Info vehiculo\n"
    "  /runt_doc <doc> — Vehiculos x propietario\n\n"
    "Comercio:\n"
    "  /rues <doc> — Registro mercantil x doc\n"
    "  /rues_nombre <nombre>\n\n"
    "Batch:\n"
    "  /full <tipo> <doc> — Todas las consultas\n\n"
    "/start /stop /status /help"
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Abriendo navegador...")
    try:
        await get_page(ADRES_URL)
        await update.effective_message.reply_text("Navegador listo.\n\n" + HELP)
    except Exception as e:
        await update.effective_message.reply_text(f"Error: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ready = await browser_ready()
    await update.effective_message.reply_text(
        "Navegador activo." if ready else "Navegador no activo. Usa /start"
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await kill_browser()
    if update and update.effective_message:
        await update.effective_message.reply_text("Navegador cerrado.")


async def _check(update: Update) -> bool:
    ready = await browser_ready()
    if not ready:
        await update.effective_message.reply_text("Navegador no activo. Usa /start")
        return False
    return True


async def _send_temp(update, text):
    return await update.effective_message.reply_text(text)


async def _send(update, msg, result):
    try:
        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                chunk = result[i:i + 4000]
                if i == 0:
                    await msg.edit_text(chunk)
                else:
                    await update.effective_message.reply_text(chunk)
        else:
            await msg.edit_text(result)
    except Exception:
        try:
            await update.effective_message.reply_text(result)
        except Exception:
            for i in range(0, len(result), 4000):
                await update.effective_message.reply_text(result[i:i + 4000])


async def cmd_adres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /adres <tipo> <doc>\n"
            "Tipos: " + ", ".join(adres.DOCUMENT_TYPES.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in adres.DOCUMENT_TYPES:
        await update.effective_message.reply_text(
            "Tipos validos: " + ", ".join(adres.DOCUMENT_TYPES.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"ADRES: consultando {doc_key} {doc_number}...")
    result = await adres.consultar(adres.DOCUMENT_TYPES[doc_key], doc_number)
    await _send(update, msg, result)


async def cmd_policia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /policia <tipo> <doc>\n"
            "Tipos: cc, ce, pa, dp"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"Policia: consultando {doc_key} {doc_number}...")
    result = await policia.consultar(doc_key, doc_number)
    await _send(update, msg, result)


async def cmd_sisben(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /sisben <tipo> <doc>\n"
            "Tipos: cc, ti, ce, rc, pasaporte, pep, ppt, dni"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    if doc_key not in sisben.SISBEN_DOC_TYPES:
        await update.effective_message.reply_text(
            "Tipos SISBEN: " + ", ".join(sisben.SISBEN_DOC_TYPES.keys())
        )
        return
    msg = await _send_temp(update, f"SISBEN: consultando {doc_key} {doc_number}...")
    result = await sisben.consultar(doc_key, doc_number)
    await _send(update, msg, result)


async def cmd_rama_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /rama_nombre <nombres> [apellidos]")
        return
    nombres = args[0]
    apellidos = " ".join(args[1:]) if len(args) > 1 else ""
    msg = await _send_temp(update, f"Rama Judicial: buscando '{nombres} {apellidos}'...")
    result = await rama_judicial.consultar_por_nombre(nombres, apellidos)
    await _send(update, msg, result)


async def cmd_rama_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /rama_doc <documento>")
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"Rama Judicial: buscando doc {doc_number}...")
    result = await rama_judicial.consultar_por_documento(doc_number)
    await _send(update, msg, result)


async def cmd_rama_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /rama_proc <radicado>")
        return
    msg = await _send_temp(update, f"Rama Judicial: buscando proceso {args[0]}...")
    result = await rama_judicial.consultar_por_proceso(args[0])
    await _send(update, msg, result)


async def cmd_procuraduria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /procuraduria <tipo> <doc>\nTipos: cc, ce, ti, pa, nit"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"Procuraduria: consultando {doc_key} {doc_number}...")
    result = await procuraduria.consultar(doc_key, doc_number)
    await _send(update, msg, result)


async def cmd_simit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /simit <tipo> <doc>\nTipos: cc, ce, ti, nit, pa"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"SIMIT: consultando {doc_key} {doc_number}...")
    result = await simit.consultar(doc_key, doc_number)
    await _send(update, msg, result)


async def cmd_runt_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /runt_placa <ABC123>")
        return
    placa = args[0].upper()
    msg = await _send_temp(update, f"RUNT: consultando placa {placa}...")
    result = await runt.consultar_vehiculo(placa)
    await _send(update, msg, result)


async def cmd_runt_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /runt_doc <documento>")
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"RUNT: consultando doc {doc_number}...")
    result = await runt.consultar_por_documento(doc_number)
    await _send(update, msg, result)


async def cmd_rues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /rues <documento_o_nit>")
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return
    msg = await _send_temp(update, f"RUES: consultando {doc_number}...")
    result = await rues.consultar_empresa(doc_number)
    await _send(update, msg, result)


async def cmd_rues_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text("Uso: /rues_nombre <nombre empresa>")
        return
    nombre = " ".join(args)
    msg = await _send_temp(update, f"RUES: buscando '{nombre}'...")
    result = await rues.consultar_por_nombre(nombre)
    await _send(update, msg, result)


async def cmd_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /full <tipo> <doc>\nEjecuta ADRES + Policia + Procuraduria + SISBEN + Rama + SIMIT"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("Numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Ejecutando TODAS las consultas para {doc_key} {doc_number}...")

    results = []

    if doc_key in adres.DOCUMENT_TYPES or doc_key == "cc":
        r = await adres.consultar(
            adres.DOCUMENT_TYPES.get(doc_key, "CC"), doc_number
        )
        results.append(r)

    r2 = await policia.consultar(doc_key, doc_number)
    results.append(r2)

    r3 = await procuraduria.consultar(doc_key, doc_number)
    results.append(r3)

    if doc_key in sisben.SISBEN_DOC_TYPES:
        r4 = await sisben.consultar(doc_key, doc_number)
        results.append(r4)

    r5 = await rama_judicial.consultar_por_documento(doc_number)
    results.append(r5)

    r6 = await simit.consultar(doc_key, doc_number)
    results.append(r6)

    combined = "\n\n".join(results)
    await _send(update, msg, combined)


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN no configurado en .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    handlers = [
        ("start", cmd_start), ("help", cmd_help), ("status", cmd_status),
        ("stop", cmd_stop), ("adres", cmd_adres), ("policia", cmd_policia),
        ("sisben", cmd_sisben), ("rama_nombre", cmd_rama_nombre),
        ("rama_doc", cmd_rama_doc), ("rama_proc", cmd_rama_proc),
        ("procuraduria", cmd_procuraduria), ("simit", cmd_simit),
        ("runt_placa", cmd_runt_placa), ("runt_doc", cmd_runt_doc),
        ("rues", cmd_rues), ("rues_nombre", cmd_rues_nombre),
        ("full", cmd_full),
    ]
    for name, handler in handlers:
        app.add_handler(CommandHandler(name, handler))

    logger.info(f"Bot con {len(handlers)} comandos iniciado.")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        try:
            from services.browser_manager import kill_browser
            asyncio.run(kill_browser())
        except Exception:
            pass


if __name__ == "__main__":
    main()
