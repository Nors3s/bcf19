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
from bs4 import BeautifulSoup

# Configura variables desde entorno (Railway o Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@BurgosCF"

# Validación de variables obligatorias
print("🔍 TELEGRAM_TOKEN:", "✅" if TELEGRAM_TOKEN else "❌ VACÍO")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")

# Noticias RSS
RSS_FEEDS = [
    "https://www.burgosdeporte.com/index.php/feed/",
    "https://revistaforofos.com/feed/",
    "https://www.burgosconecta.es/burgoscf/rss",
    "https://www.diariodeburgos.es/seccion/burgos+cf/f%C3%BAtbol/deportes/rss"
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None
posted_titles = set()

def start(update: Update, context: CallbackContext):
    update.message.reply_text('¡Bot del Burgos CF en marcha!')

def fetch_news():
    mensajes = []
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

def send_news(context: CallbackContext):
    noticias = fetch_news()
    for noticia in noticias:
        context.bot.send_message(chat_id=CHANNEL_ID, text=noticia)

import asyncio
from playwright.async_api import async_playwright

def send_next_match(context: CallbackContext):
    asyncio.run(scrape_flashscore(context))

async def scrape_flashscore(context: CallbackContext):
    print("📡 Buscando próximos partidos del Burgos CF (Playwright/Flashscore)...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.flashscore.com/team/burgos-cf/vTxTEFi6/")
            await page.wait_for_selector("div.event__match")

            partidos = await page.query_selector_all("div.event__match")
            for p in partidos:
                clase = await p.get_attribute("class")
                if "event__match--scheduled" in clase:
                    hora = await p.query_selector(".event__time")
                    local = await p.query_selector(".event__participant--home")
                    visitante = await p.query_selector(".event__participant--away")

                    hora_text = await hora.inner_text() if hora else ""
                    local_text = await local.inner_text() if local else ""
                    visitante_text = await visitante.inner_text() if visitante else ""

                    mensaje = f"📅 Próximo partido del Burgos CF:
🏟️ {local_text} vs {visitante_text}
🕒 Hora: {hora_text}"
                    await browser.close()
                    context.bot.send_message(chat_id=CHANNEL_ID, text=mensaje)
                    return

            await browser.close()
            context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente.")

    except Exception as e:
        context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚠️ Error con Flashscore: {e}")

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)

    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))

    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
