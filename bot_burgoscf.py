import logging
import requests
import feedparser
import os
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.update import Update
import time
from datetime import datetime, timedelta
import pytz
import json

# Configura variables desde entorno (Railway o Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BESOCCER_API_TOKEN = os.getenv("BESOCCER_API_TOKEN")
CHANNEL_ID = "@BurgosCF"  # <-- CAMBIA esto por tu canal real si no lo has hecho

# Validación de variables obligatorias
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")
if not BESOCCER_API_TOKEN:
    raise ValueError("❌ BESOCCER_API_TOKEN no está definido. Añádelo como variable de entorno.")

BESOCCER_API_URL = "https://apiv2.besoccer.com"
TEAM_NAME = "burgos"

# Noticias RSS
RSS_FEEDS = [
    "https://www.burgosdeporte.com/index.php/feed/",
    "https://revistaforofos.com/feed/"
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

def get_next_match():
    print("📡 Buscando próximos partidos del Burgos CF (vía BeSoccer)...")
    url = f"{BESOCCER_API_URL}/matches/team/next/"  # Endpoint genérico, puede necesitar ajuste según la documentación
    params = {
        "token": BESOCCER_API_TOKEN,
        "format": "json",
        "team": TEAM_NAME,
        "tz": "Europe/Madrid"
    }
    response = requests.get(url, params=params)
    print(f"🔧 Status code: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    if "matches" in data and data["matches"]:
        return data["matches"][0]  # Primer partido
    return None

# Guarda los eventos ya publicados
posted_events = set()

def seguimiento_partido(context: CallbackContext):
    partido = get_next_match()
    if not partido:
        context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente.")
        return

    local = partido['local']['name']
    visitante = partido['visitor']['name']
    fecha_str = partido['date']

    fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
    fecha_madrid = fecha_obj.astimezone(pytz.timezone("Europe/Madrid"))
    fecha_formateada = fecha_madrid.strftime("%A, %d de %B a las %H:%M")

    info_partido = f"🏟️ {local} vs {visitante}\n🗓️ {fecha_formateada} (hora española)"
    context.bot.send_message(chat_id=CHANNEL_ID, text=f"🏁 ¡Empieza el seguimiento del próximo partido!\n{info_partido}")

    # ⚠️ Aquí puedes añadir seguimiento de eventos si BeSoccer lo permite en el plan

def main():
    global bot
    bot = Bot(token=TELEGRAM_TOKEN)

    updater = Updater(token=TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))

    updater.job_queue.run_repeating(send_news, interval=3600, first=10)
    updater.job_queue.run_once(seguimiento_partido, when=30)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
