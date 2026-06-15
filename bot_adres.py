import os
import logging
import asyncio

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from services import adres, policia, sisben, rama_judicial, procuraduria, simit, runt, rues
from services.browser_manager import kill_browser, get_page, browser_ready

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADRES_URL = adres.ADRES_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "*BOT DE CONSULTAS COLOMBIA*\n"
    "===============================\n"
    "*Salud y Seguridad Social:*\n"
    "  /adres <tipo> <numero> - Afiliacion EPS (cedula, ti, ce, rc, pasaporte...)\n"
    "  /sisben <tipo> <numero> - Grupo Sisben IV (cedula, ti, ce, rc)\n"
    "\n"
    "*Antecedentes y Judicial:*\n"
    "  /policia <tipo> <numero> - Antecedentes judiciales (cedula, ti, ce)\n"
    "  /procuraduria <tipo> <numero> - Antecedentes disciplinarios\n"
    "  /rama_nombre <nombre> <apellido> - Procesos judiciales por nombre\n"
    "  /rama_doc <numero> - Procesos judiciales por documento\n"
    "  /rama_proc <numero> - Procesos judiciales por radicado\n"
    "\n"
    "*Transito y Vehiculos:*\n"
    "  /simit <tipo> <numero> - Multas de transito (cedula, nit)\n"
    "  /runt_placa <placa> - Informacion vehicular por placa (ABC123)\n"
    "  /runt_doc <numero> - Vehiculos por documento del propietario\n"
    "\n"
    "*Comercio:*\n"
    "  /rues <numero> - Registro mercantil por documento\n"
    "  /rues_nombre <nombre> - Registro mercantil por nombre\n"
    "\n"
    "*Batch:*\n"
    "  /full <tipo> <numero> - Todas las consultas para una persona\n"
    "\n"
    "*Utilidades:*\n"
    "  /start - Abrir navegador\n"
    "  /stop - Cerrar navegador\n"
    "  /status - Ver estado del navegador\n"
    "  /help - Este mensaje\n"
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Abriendo navegador...\n" + HELP_TEXT,
        parse_mode="Markdown",
    )
    try:
        await get_page(ADRES_URL)
        await update.effective_message.reply_text("Navegador listo.")
    except Exception as e:
        await update.effective_message.reply_text(f"Error al abrir navegador: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ready = await browser_ready()
    if ready:
        await update.effective_message.reply_text("Navegador activo y funcionando.")
    else:
        await update.effective_message.reply_text(
            "Navegador no activo. Usa /start para abrirlo."
        )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await kill_browser()
    if update and update.effective_message:
        await update.effective_message.reply_text("Navegador cerrado.")


async def cmd_adres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /adres <tipo> <numero>\nEj: /adres cedula 888811111\n"
            "Tipos: " + ", ".join(adres.DOCUMENT_TYPES.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in adres.DOCUMENT_TYPES:
        await update.effective_message.reply_text(
            "Tipo invalido. Validos: " + ", ".join(adres.DOCUMENT_TYPES.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando ADRES: {doc_key} {doc_number}...")
    result = await adres.consultar(adres.DOCUMENT_TYPES[doc_key], doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_policia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /policia <tipo> <numero>\nEj: /policia cedula 888811111\n"
            "Tipos: " + ", ".join(policia.DOCUMENT_TYPES_POLICIA.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in policia.DOCUMENT_TYPES_POLICIA:
        await update.effective_message.reply_text(
            "Tipo invalido. Validos: " + ", ".join(policia.DOCUMENT_TYPES_POLICIA.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando Policia: {doc_key} {doc_number}...")
    result = await policia.consultar(doc_key, doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_sisben(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /sisben <tipo> <numero>\nEj: /sisben cedula 888811111\n"
            "Tipos: " + ", ".join(sisben.DOCUMENT_TYPES_SISBEN.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in sisben.DOCUMENT_TYPES_SISBEN:
        await update.effective_message.reply_text(
            "Tipo invalido. Validos: " + ", ".join(sisben.DOCUMENT_TYPES_SISBEN.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando SISBEN: {doc_key} {doc_number}...")
    result = await sisben.consultar(doc_key, doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_rama_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /rama_nombre <nombres> [apellidos]\nEj: /rama_nombre Juan Perez"
        )
        return
    nombres = args[0]
    apellidos = " ".join(args[1:]) if len(args) > 1 else ""

    msg = await _send_temp(update, f"Consultando Rama Judicial por nombre: {nombres} {apellidos}...")
    result = await rama_judicial.consultar_por_nombre(nombres, apellidos)
    await _edit_or_reply(update, msg, result)


async def cmd_rama_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /rama_doc <numero_documento>\nEj: /rama_doc 888811111"
        )
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando Rama Judicial por doc: {doc_number}...")
    result = await rama_judicial.consultar_por_documento(doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_rama_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /rama_proc <numero_proceso>\nEj: /rama_proc 11001400300120240000100"
        )
        return
    numero_proceso = args[0]

    msg = await _send_temp(update, f"Consultando Rama Judicial por proceso: {numero_proceso}...")
    result = await rama_judicial.consultar_por_proceso(numero_proceso)
    await _edit_or_reply(update, msg, result)


async def cmd_procuraduria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /procuraduria <tipo> <numero>\nEj: /procuraduria cedula 888811111\n"
            "Tipos: " + ", ".join(procuraduria.DOCUMENT_TYPES_PROC.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in procuraduria.DOCUMENT_TYPES_PROC:
        await update.effective_message.reply_text(
            "Tipo invalido. Validos: " + ", ".join(procuraduria.DOCUMENT_TYPES_PROC.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando Procuraduria: {doc_key} {doc_number}...")
    result = await procuraduria.consultar(doc_key, doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_simit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /simit <tipo> <numero>\nEj: /simit cedula 888811111\n"
            "Tipos: " + ", ".join(simit.DOCUMENT_TYPES_SIMIT.keys())
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]
    if doc_key not in simit.DOCUMENT_TYPES_SIMIT:
        await update.effective_message.reply_text(
            "Tipo invalido. Validos: " + ", ".join(simit.DOCUMENT_TYPES_SIMIT.keys())
        )
        return
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando SIMIT: {doc_key} {doc_number}...")
    result = await simit.consultar(doc_key, doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_runt_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /runt_placa <placa>\nEj: /runt_placa ABC123"
        )
        return
    placa = args[0].upper()

    msg = await _send_temp(update, f"Consultando RUNT placa: {placa}...")
    result = await runt.consultar_vehiculo(placa)
    await _edit_or_reply(update, msg, result)


async def cmd_runt_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /runt_doc <numero_documento>\nEj: /runt_doc 888811111"
        )
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando RUNT por documento: {doc_number}...")
    result = await runt.consultar_por_documento(doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_rues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /rues <numero_documento>\nEj: /rues 888811111"
        )
        return
    doc_number = args[0]
    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Consultando RUES: {doc_number}...")
    result = await rues.consultar_empresa(doc_number)
    await _edit_or_reply(update, msg, result)


async def cmd_rues_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 1:
        await update.effective_message.reply_text(
            "Uso: /rues_nombre <nombre>\nEj: /rues_nombre \"Empresa SAS\""
        )
        return
    nombre = " ".join(args)

    msg = await _send_temp(update, f"Consultando RUES por nombre: {nombre}...")
    result = await rues.consultar_por_nombre(nombre)
    await _edit_or_reply(update, msg, result)


async def cmd_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_browser(update):
        return
    args = context.args
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Uso: /full <tipo> <numero>\nEj: /full cedula 888811111\n"
            "Ejecuta ADRES + Policia + Procuraduria + SISBEN + Rama Judicial + SIMIT"
        )
        return
    doc_key = args[0].lower()
    doc_number = args[1]

    if not doc_number.isdigit():
        await update.effective_message.reply_text("El numero debe ser numerico.")
        return

    msg = await _send_temp(update, f"Ejecutando todas las consultas para {doc_key} {doc_number}...")

    results = []

    if doc_key in adres.DOCUMENT_TYPES:
        results.append(await adres.consultar(adres.DOCUMENT_TYPES[doc_key], doc_number))

    if doc_key in policia.DOCUMENT_TYPES_POLICIA:
        results.append(await policia.consultar(doc_key, doc_number))

    if doc_key in procuraduria.DOCUMENT_TYPES_PROC:
        results.append(await procuraduria.consultar(doc_key, doc_number))

    if doc_key in sisben.DOCUMENT_TYPES_SISBEN:
        results.append(await sisben.consultar(doc_key, doc_number))

    results.append(await rama_judicial.consultar_por_documento(doc_number))

    if doc_key in simit.DOCUMENT_TYPES_SIMIT:
        results.append(await simit.consultar(doc_key, doc_number))

    combined = "\n\n".join(results)
    await _edit_or_reply(update, msg, combined)


async def _check_browser(update: Update) -> bool:
    ready = await browser_ready()
    if not ready:
        await update.effective_message.reply_text(
            "Navegador no activo. Usa /start para iniciarlo."
        )
        return False
    return True


async def _send_temp(update: Update, text: str):
    return await update.effective_message.reply_text(text)


async def _edit_or_reply(update: Update, msg, result: str):
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


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN no configurado en .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("adres", cmd_adres))
    app.add_handler(CommandHandler("policia", cmd_policia))
    app.add_handler(CommandHandler("sisben", cmd_sisben))
    app.add_handler(CommandHandler("rama_nombre", cmd_rama_nombre))
    app.add_handler(CommandHandler("rama_doc", cmd_rama_doc))
    app.add_handler(CommandHandler("rama_proc", cmd_rama_proc))
    app.add_handler(CommandHandler("procuraduria", cmd_procuraduria))
    app.add_handler(CommandHandler("simit", cmd_simit))
    app.add_handler(CommandHandler("runt_placa", cmd_runt_placa))
    app.add_handler(CommandHandler("runt_doc", cmd_runt_doc))
    app.add_handler(CommandHandler("rues", cmd_rues))
    app.add_handler(CommandHandler("rues_nombre", cmd_rues_nombre))
    app.add_handler(CommandHandler("full", cmd_full))

    logger.info("Bot iniciado con 16 comandos.")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        try:
            from services.browser_manager import kill_browser
            import asyncio as aio
            aio.run(kill_browser())
        except Exception:
            pass


if __name__ == "__main__":
    main()
