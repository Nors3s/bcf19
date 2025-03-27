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

# Integración con Bluesky
def fetch_bluesky_posts():
    url = "https://bsky.social/xrpc/app.bsky.feed.getActorTimeline"
    params = {
        "actor": "burgoscf.bsky.social",
        "limit": 10
    }
    headers = {
        "Accept": "application/json"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if "feed" in data:
            return data["feed"]
    return []

def send_bluesky_posts(context: CallbackContext):
    posts = fetch_bluesky_posts()
    for post in posts:
        # Extraemos un identificador único para evitar duplicados
        post_id = post.get("post", {}).get("cid") or post.get("post", {}).get("uri")
        if post_id and post_id not in posted_bluesky_ids:
            text = post.get("post", {}).get("text", "")
            created_at = post.get("post", {}).get("createdAt", "")
            message = f"🌀 Bluesky:\n{text}\n🕒 {created_at}"
            context.bot.send_message(chat_id=CHANNEL_ID, text=message)
            posted_bluesky_ids.add(post_id)

# Función para obtener el próximo partido mediante scraping en Flashscore usando Playwright
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
                    return
            
            await browser.close()
            context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente en Flashscore.")
    except Exception as e:
        context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚠️ Error con Flashscore: {e}")

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)
    
    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Programar envío de noticias cada 1 hora
    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    # Programar envío de posts de Bluesky cada 1 hora
    updater.job_queue.run_repeating(send_bluesky_posts, interval=3600, first=20)
    # Programar envío del próximo partido cada 4 horas
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
