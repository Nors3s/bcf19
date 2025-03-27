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

# Configura variables desde entorno (Railway o Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
CHANNEL_ID = "@BurgosCF"  # <-- CAMBIA esto por tu canal real si no lo has hecho

# Validación de variables obligatorias
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido. Añádelo como variable de entorno.")
if not FOOTBALL_API_KEY:
    raise ValueError("❌ FOOTBALL_API_KEY no está definido. Añádelo como variable de entorno.")

FOOTBALL_API_URL = "https://v3.football.api-sports.io"
TEAM_ID_BURGOS = 2826  # ID del Burgos CF en API-Football (LaLiga SmartBank)
LEAGUE_ID = 141  # Segunda División España
SEASON = 2024

# Noticias RSS
RSS_FEEDS = [
    "https://www.burgosdeporte.com/index.php/feed/",
    "https://revistaforofos.com/feed/"
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None
posted_titles = set()
headers_api = {
    "x-apisports-key": FOOTBALL_API_KEY
}

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
    print("📡 Buscando próximos partidos del Burgos CF...")
    hoy = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"{FOOTBALL_API_URL}/fixtures?team={TEAM_ID_BURGOS}&season={SEASON}&from={hoy}&limit=50&timezone=UTC"
    response = requests.get(url, headers=headers_api)
    data = response.json()
    partidos = data.get("response", [])

    print(f"🔍 Total partidos recibidos: {len(partidos)}")
    for p in partidos:
        estado = p['fixture']['status']['short']
        fecha = p['fixture']['date']
        local = p['teams']['home']['name']
        visitante = p['teams']['away']['name']
        print(f" - {fecha} | {local} vs {visitante} | Estado: {estado}")

    futuros = [p for p in partidos if p["fixture"]["status"]["short"] in ["NS", "TBD"]]

    if futuros:
        partidos_ordenados = sorted(futuros, key=lambda x: x["fixture"]["date"])
        return partidos_ordenados[0]
    return None

# Guarda los eventos ya publicados
posted_events = set()

def seguimiento_partido(context: CallbackContext):
    partido = get_next_match()
    if not partido:
        context.bot.send_message(chat_id=CHANNEL_ID, text="❌ No hay partido programado próximamente.")
        return

    fixture_id = partido["fixture"]["id"]
    equipos = partido["teams"]
    fecha_utc = datetime.strptime(partido["fixture"]["date"], "%Y-%m-%dT%H:%M:%S%z")
    fecha_madrid = fecha_utc.astimezone(pytz.timezone("Europe/Madrid"))
    fecha_formateada = fecha_madrid.strftime("%A, %d de %B a las %H:%M")

    info_partido = f"🏟️ {equipos['home']['name']} vs {equipos['away']['name']}\n🗓️ {fecha_formateada} (hora española)"
    context.bot.send_message(chat_id=CHANNEL_ID, text=f"🏁 ¡Empieza el seguimiento del próximo partido!\n{info_partido}")

    while True:
        eventos_url = f"{FOOTBALL_API_URL}/fixtures/events?fixture={fixture_id}"
        eventos_res = requests.get(eventos_url, headers=headers_api).json()
        for evento in eventos_res["response"]:
            key = f"{evento['time']['elapsed']}-{evento['team']['id']}-{evento['player']['name']}-{evento['type']}"
            if key not in posted_events:
                minuto = evento['time']['elapsed']
                tipo = evento['type']
                detalle = evento['detail']
                jugador = evento['player']['name']
                texto = ""
                if tipo == "Goal":
                    texto = f"⚽️ ¡Gol de {jugador}! ({minuto}')"
                elif tipo == "Card":
                    emoji = "🟨" if detalle == "Yellow Card" else "🟥"
                    texto = f"{emoji} Tarjeta para {jugador} ({minuto}')"
                elif tipo == "subst":
                    texto = f"🔁 Cambio: {jugador} entra ({minuto}')"

                if texto:
                    context.bot.send_message(chat_id=CHANNEL_ID, text=texto)
                    posted_events.add(key)
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

