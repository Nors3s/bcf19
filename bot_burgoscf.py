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
SPORTMONKS_API_TOKEN = os.getenv("SPORTMONKS_API_TOKEN")
CHANNEL_ID = "@BurgosCF"

# Validación de variables obligatorias
print("🔍 TELEGRAM_TOKEN:", "✅" if TELEGRAM_TOKEN else "❌ VACÍO")
print("🔍 SPORTMONKS_API_TOKEN:", "✅" if SPORTMONKS_API_TOKEN else "❌ VACÍO")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")
if not SPORTMONKS_API_TOKEN:
    raise ValueError("❌ SPORTMONKS_API_TOKEN no está definido. Añádelo como variable de entorno.")

SPORTMONKS_API_URL = "https://api.sportmonks.com/v3/football"
TEAM_ID = 1873  # Burgos CF en Sportmonks

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
    print("📡 Buscando próximos partidos del Burgos CF (vía Sportmonks)...")
    url = f"{SPORTMONKS_API_URL}/teams/{TEAM_ID}/fixtures"
    params = {
        "api_token": SPORTMONKS_API_TOKEN,
        "sort": "starting_at",
        "include": "localTeam,visitorTeam",
        "per_page": 1
    }
    response = requests.get(url, params=params)
    print(f"🔧 Status code: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    if "data" in data and data["data"]:
        return data["data"][0]
    return None

# Guarda los eventos ya publicados
posted_events = set()

def seguimiento_partido(context: CallbackContext):
    partido = get_next_match()
    if not partido:
        context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente.")
        return

    fixture_id = partido['id']
    local = partido['localTeam']['data']['name']
    visitante = partido['visitorTeam']['data']['name']
    fecha_str = partido['starting_at']
    fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S%z")
    fecha_madrid = fecha_obj.astimezone(pytz.timezone("Europe/Madrid"))
    fecha_formateada = fecha_madrid.strftime("%A, %d de %B a las %H:%M")

    info_partido = f"🏟️ {local} vs {visitante}
🗓️ {fecha_formateada} (hora española)"
    context.bot.send_message(chat_id=CHANNEL_ID, text=f"🏁 ¡Empieza el seguimiento del próximo partido!
{info_partido}")

    # Seguimiento en tiempo real (eventos)
    partido_finalizado = False
    while not partido_finalizado:
        eventos_url = f"{SPORTMONKS_API_URL}/fixtures/{fixture_id}?include=events"
        params = {"api_token": SPORTMONKS_API_TOKEN}
        res = requests.get(eventos_url, params=params)
        data = res.json()

        # Verificar si el partido ha finalizado
        status = data.get("data", {}).get("status")
        if status and status.lower() in ["ft", "fulltime", "ended"]:
            marcador_local = data["data"].get("scores", {}).get("local_score", "?")
            marcador_visitante = data["data"].get("scores", {}).get("visitor_score", "?")
            resultado = f"⏱️ Final del partido: {local} {marcador_local} - {marcador_visitante} {visitante}"
            context.bot.send_message(chat_id=CHANNEL_ID, text=resultado)
            break

        if "data" in data and "events" in data["data"] and "data" in data["data"]["events"]:
            for evento in data["data"]["events"]["data"]:
                event_id = evento.get("id")
                if event_id in posted_events:
                    continue
                posted_events.add(event_id)

                tipo = evento.get("type")
                jugador = evento.get("player_name", "")
                minuto = evento.get("minute", "")
                texto = ""

                if tipo == "goal":
                    texto = f"⚽️ ¡Gol de {jugador}! ({minuto}')"
                elif tipo == "yellowcard":
                    texto = f"🟨 Tarjeta amarilla para {jugador} ({minuto}')"
                elif tipo == "redcard":
                    texto = f"🟥 Tarjeta roja para {jugador} ({minuto}')"
                elif tipo == "substitution":
                    texto = f"🔁 Cambio: {jugador} entra ({minuto}')"

                if texto:
                    context.bot.send_message(chat_id=CHANNEL_ID, text=texto)

        time.sleep(60)

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
