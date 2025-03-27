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

def send_next_match(context: CallbackContext):
    print("📡 Buscando próximos partidos del Burgos CF (scraping burgosdeporte.com)...")
    url = "https://www.burgosdeporte.com/index.php/category/burgos-cf/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    posibles = soup.find_all("article", limit=5)
    for post in posibles:
        titulo = post.find("h2")
        enlace = post.find("a")
        if titulo and "previa" in titulo.text.lower():
            mensaje = f"📅 Próximo partido del Burgos CF (previsto):\n🗞️ {titulo.text.strip()}\n🔗 {enlace['href']}"
            context.bot.send_message(chat_id=CHANNEL_ID, text=mensaje)
            return
    context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No se ha encontrado información de próximo partido.")

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
