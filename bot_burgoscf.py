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

# Validación de variables obligatorias
print("🔍 TELEGRAM_TOKEN:", "✅" if TELEGRAM_TOKEN else "❌ VACÍO")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None
posted_titles = set()
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

# Función para enviar noticias a Telegram
def send_news(context: CallbackContext):
    noticias = fetch_news()
    for noticia in noticias:
        context.bot.send_message(chat_id=CHANNEL_ID, text=noticia)

# Función para obtener posts de Bluesky
def fetch_bluesky_posts():
    url = "https://bsky.social/xrpc/app.bsky.feed.getActorTimeline"
    params = {
        "actor": "burgoscf.bsky.social",
        "limit": 10
    }
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, params=params, headers=headers)
        logger.info("Bluesky response status: %s", response.status_code)
        data = response.json()
        logger.info("Bluesky response JSON: %s", json.dumps(data, indent=2))
    except Exception as ex:
        logger.error("Error obteniendo o parseando Bluesky JSON: %s", ex)
        return []
    if "feed" in data:
        return data["feed"]
    else:
        logger.warning("La respuesta de Bluesky no contiene la clave 'feed'")
    return []

# Función para enviar posts de Bluesky a Telegram
def send_bluesky_posts(context: CallbackContext):
    posts = fetch_bluesky_posts()
    if not posts:
        logger.warning("No se han obtenido posts de Bluesky.")
    for post in posts:
        logger.info("Procesando post: %s", post)
        post_data = post.get("post", {})
        post_id = post_data.get("cid") or post_data.get("uri")
        if not post_id:
            logger.warning("No se encontró ID en el post: %s", post)
            continue
        if post_id in posted_bluesky_ids:
            logger.info("El post %s ya fue enviado.", post_id)
            continue
        text = post_data.get("text", "")
        created_at = post_data.get("createdAt", "")
        message = f"🌀 Bluesky:\n{text}\n🕒 {created_at}"
        context.bot.send_message(chat_id=CHANNEL_ID, text=message)
        posted_bluesky_ids.add(post_id)

# Función para obtener la programación de próximos partidos (en este ejemplo, se asume que la integración con Flashscore se mantiene, pero si falla, se puede ajustar)
def send_next_match(context: CallbackContext):
    # Si se desea integrar con Flashscore, se llamaría a una función aquí.
    # En este ejemplo, eliminamos el scraping de Flashscore, así que se enviará un mensaje informativo.
    context.bot.send_message(chat_id=CHANNEL_ID, text="ℹ️ Funcionalidad de próximos partidos no implementada actualmente.")

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)
    
    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Programar el envío de noticias cada 1 hora
    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    # Programar el envío de posts de Bluesky cada 1 hora
    updater.job_queue.run_repeating(send_bluesky_posts, interval=3600, first=20)
    # Programar el envío de la programación de próximos partidos (en este ejemplo, solo un mensaje informativo)
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
