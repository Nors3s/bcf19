import logging
import requests
import feedparser
import os
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.update import Update
from datetime import datetime
import pytz
import json
import asyncio
from playwright.async_api import async_playwright

# Configura variables desde entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@BurgosCF")
BLUESKY_TOKEN = os.getenv("BLUESKY_TOKEN")  # Token para publicar en Bluesky

# Validación de variables obligatorias
print("🔍 TELEGRAM_TOKEN:", "✅" if TELEGRAM_TOKEN else "❌ VACÍO")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None
posted_titles = set()
# Usamos posted_bluesky_ids para evitar duplicados si fuera necesario (en este ejemplo no se usa para publicar, solo para evitar reenvíos)
posted_bluesky_ids = set()

# Función de inicio para Telegram
def start(update: Update, context: CallbackContext):
    update.message.reply_text('¡Bot del Burgos CF en marcha!')

# Función para obtener noticias desde feeds RSS
def fetch_news():
    mensajes = []
    RSS_FEEDS = [
        "https://www.burgosdeporte.com/index.php/feed/",
        "https://revistaforofos.com/feed/",
        "https://www.burgosconecta.es/burgoscf/rss",
        "https://www.diariodeburgos.es/seccion/burgos+cf/f%C3%BAtbol/deportes/rss"
    ]
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:
            titulo = entry.title.lower()
            resumen = entry.summary.lower()
            if "burgos cf" in titulo or "burgos cf" in resumen:
                if entry.title not in posted_titles:
                    mensaje = f"🗞️ {entry.title}\n{entry.link}"
                    mensajes.append(mensaje)
                    posted_titles.add(entry.title)
    return mensajes

# Función para enviar noticias a Telegram y Bluesky
def send_news(context: CallbackContext):
    noticias = fetch_news()
    for noticia in noticias:
        context.bot.send_message(chat_id=CHANNEL_ID, text=noticia)
        send_to_bluesky(noticia)

# Función para enviar un mensaje a Bluesky mediante la API de Bluesky
def send_to_bluesky(message: str):
    if not BLUESKY_TOKEN:
        logger.warning("BLUESKY_TOKEN no definido; no se enviará a Bluesky.")
        return
    url = "https://bsky.social/xrpc/app.bsky.feed.post"
    headers = {
        "Authorization": f"Bearer {BLUESKY_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": message
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info("Mensaje enviado a Bluesky correctamente.")
        else:
            logger.error("Error enviando mensaje a Bluesky: %s %s", response.status_code, response.text)
    except Exception as e:
        logger.error("Excepción al enviar mensaje a Bluesky: %s", e)

# Función para obtener la programación del próximo partido
# (En este ejemplo, se mantiene la integración con Flashscore para extraer la info)
def send_next_match(context: CallbackContext):
    asyncio.run(scrape_flashscore(context))

async def scrape_flashscore(context: CallbackContext):
    print("📡 Buscando próximos partidos del Burgos CF (Playwright/Flashscore)...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Usamos la URL de Flashscore para el Burgos CF
            await page.goto("https://www.flashscore.com/team/burgos-cf/vTxTEFi6/")
            await page.wait_for_selector("div.event__match")
            
            partidos = await page.query_selector_all("div.event__match")
            for elem in partidos:
                clase = await elem.get_attribute("class")
                if "event__match--scheduled" in clase:
                    hora_elem = await elem.query_selector(".event__time")
                    local_elem = await elem.query_selector(".event__participant--home")
                    visitante_elem = await elem.query_selector(".event__participant--away")
                    
                    hora_text = await hora_elem.inner_text() if hora_elem else ""
                    local_text = await local_elem.inner_text() if local_elem else ""
                    visitante_text = await visitante_elem.inner_text() if visitante_elem else ""
                    
                    mensaje = f"📅 Próximo partido del Burgos CF:\n🏟️ {local_text} vs {visitante_text}\n🕒 Hora: {hora_text}"
                    await browser.close()
                    context.bot.send_message(chat_id=CHANNEL_ID, text=mensaje)
                    send_to_bluesky(mensaje)
                    return
            
            await browser.close()
            # Si no se encuentra partido, no se envía mensaje (según tu solicitud)
            logger.info("No se encontró información de próximo partido en Flashscore.")
    except Exception as e:
        context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚠️ Error con Flashscore: {e}")
        send_to_bluesky(f"⚠️ Error con Flashscore: {e}")

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)
    
    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Programa el envío de noticias cada 1 hora
    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    # Programa el envío de posts de Bluesky (ahora ya no se recuperan, sino que se envía lo que se publique en Telegram)
    # En este ejemplo, la integración con Bluesky se realiza en send_news y send_next_match, enviando el mismo mensaje.
    
    # Programa el envío del próximo partido cada 4 horas
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
