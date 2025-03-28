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
BLUESKY_TOKEN = os.getenv("BLUESKY_TOKEN")  # Si no tienes token, la integración de Bluesky no enviará posts

# Validación de variables obligatorias para Telegram
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
        "Authorization": f"Bearer {BLUESKY_TOKEN}",
        "Accept": "application/json"
    }
    response = requests.get(url, params=params, headers=headers)
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

# Función para obtener la programación del próximo partido (se usa Flashscore con Playwright)
def send_next_match(context: CallbackContext):
    asyncio.run(scrape_flashscore(context))

async def scrape_flashscore(context: CallbackContext):
    print("📡 Buscando próximos partidos del Burgos CF (Playwright/Flashscore)...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.flashscore.com/team/burgos-cf/vTxTEFi6/")
            await page.wait_for_selector("div.event__match", timeout=10000)
            
            partidos = await page.query_selector_all("div.event__match")
            for elem in partidos:
                clase = await elem.get_attribute("class")
                if "event__match--scheduled" in clase:
                    participantes = await elem.query_selector_all(".event__participant")
                    if len(participantes) >= 2:
                        home_text = (await participantes[0].inner_text()).strip()
                        away_text = (await participantes[1].inner_text()).strip()
                    else:
                        home_text, away_text = "", ""
                    
                    hora_elem = await elem.query_selector(".event__time")
                    hora_text = (await hora_elem.inner_text()).strip() if hora_elem else ""
                    
                    # Solo se publica si se tienen todos los datos
                    if home_text and away_text and hora_text:
                        mensaje = f"📅 Próximo partido del Burgos CF:\n🏟️ {home_text} vs {away_text}\n🕒 Hora: {hora_text}"
                        await browser.close()
                        context.bot.send_message(chat_id=CHANNEL_ID, text=mensaje)
                        return
            
            await browser.close()
            print("No se encontró información completa de próximo partido en Flashscore.")
    except Exception as e:
        context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚠️ Error con Flashscore: {e}")

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)
    
    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Programa el envío de noticias cada 1 hora
    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    # Programa el envío de posts de Bluesky cada 1 hora
    updater.job_queue.run_repeating(send_bluesky_posts, interval=3600, first=20)
    # Programa el envío del próximo partido cada 4 horas
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
