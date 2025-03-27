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

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def send_next_match(context: CallbackContext):
    print("📡 Buscando próximos partidos del Burgos CF (Selenium/Flashscore)...")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.get("https://www.flashscore.es/equipo/burgos/8bU7z2d6/")

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.event__match"))
        )

        partidos = driver.find_elements(By.CSS_SELECTOR, "div.event__match")
        for p in partidos:
            estado = p.get_attribute("class")
            if "event__match--scheduled" in estado:
                hora = p.find_element(By.CLASS_NAME, "event__time").text
                local = p.find_element(By.CLASS_NAME, "event__participant--home").text
                visitante = p.find_element(By.CLASS_NAME, "event__participant--away").text
                mensaje = f"📅 Próximo partido del Burgos CF:
🏟️ {local} vs {visitante}
🕒 Hora: {hora}"
                context.bot.send_message(chat_id=CHANNEL_ID, text=mensaje)
                break
        else:
            context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente.")

    except Exception as e:
        context.bot.send_message(chat_id=CHANNEL_ID, text=f"⚠️ Error al buscar el partido: {e}")
    finally:
        driver.quit()

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
