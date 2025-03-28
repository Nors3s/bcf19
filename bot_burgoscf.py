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

# --- Configuración de variables de entorno ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@BurgosCF")
# Token de Bluesky (Access Token) y Refresh Token
BLUESKY_TOKEN = os.getenv("BLUESKY_TOKEN")
BLUESKY_REFRESH_TOKEN = os.getenv("BLUESKY_REFRESH_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está definido.")
if not BLUESKY_TOKEN:
    logging.warning("BLUESKY_TOKEN no está definido; la integración de Bluesky no funcionará.")
if not BLUESKY_REFRESH_TOKEN:
    logging.warning("BLUESKY_REFRESH_TOKEN no está definido; no se podrá renovar el token automáticamente.")

# --- Configuración de logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None
posted_titles = set()
posted_bluesky_ids = set()

# Variable global para el token actual de Bluesky
current_bluesky_token = BLUESKY_TOKEN

# --- Función para renovar el token de Bluesky ---
def refresh_bluesky_token():
    global current_bluesky_token, BLUESKY_REFRESH_TOKEN
    refresh_url = "https://bsky.social/xrpc/com.atproto.server.refreshSession"  # Verifica este endpoint
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "refreshToken": BLUESKY_REFRESH_TOKEN
    }
    try:
        response = requests.post(refresh_url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            new_access = data.get("accessJwt")
            new_refresh = data.get("refreshJwt")
            if new_access:
                current_bluesky_token = new_access
                BLUESKY_REFRESH_TOKEN = new_refresh  # Actualiza el refresh token, si se proporciona
                logger.info("Token de Bluesky renovado correctamente.")
                return True
            else:
                logger.error("No se recibió 'accessJwt' en la respuesta de renovación.")
                return False
        else:
            logger.error("Error al renovar token de Bluesky: %s %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.error("Excepción al renovar token de Bluesky: %s", e)
        return False

# --- Función para obtener posts de Bluesky ---
def fetch_bluesky_posts():
    url = "https://bsky.social/xrpc/app.bsky.feed.getActorTimeline"
    params = {
        "actor": "burgoscf.bsky.social",
        "limit": 10
    }
    headers = {
        "Authorization": f"Bearer {current_bluesky_token}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, params=params, headers=headers)
        logger.info("Bluesky response status: %s", response.status_code)
        data = response.json()
        logger.info("Bluesky response JSON: %s", json.dumps(data, indent=2))
    except Exception as ex:
        logger.error("Error al obtener posts de Bluesky: %s", ex)
        return []
    # Si se recibe un error de token expirado, renovar y reintentar
    if response.status_code == 401 and data.get("error") == "ExpiredToken":
        logger.warning("Token expirado, renovando...")
        if refresh_bluesky_token():
            return fetch_bluesky_posts()  # reintentar con el nuevo token
        else:
            return []
    if "feed" in data:
        return data["feed"]
    else:
        logger.warning("La respuesta de Bluesky no contiene 'feed'.")
        return []

# --- Función para enviar posts de Bluesky a Telegram ---
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

# --- Función para obtener noticias desde feeds RSS ---
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

# --- Función para enviar noticias a Telegram y Bluesky ---
def send_news(context: CallbackContext):
    noticias = fetch_news()
    for noticia in noticias:
        context.bot.send_message(chat_id=CHANNEL_ID, text=noticia)
        send_to_bluesky(noticia)

# --- Función para enviar un mensaje a Bluesky ---
def send_to_bluesky(message: str):
    if not BLUESKY_TOKEN:
        logger.warning("BLUESKY_TOKEN no definido; no se enviará a Bluesky.")
        return
    url = "https://bsky.social/xrpc/app.bsky.feed.post"
    headers = {
        "Authorization": f"Bearer {current_bluesky_token}",
        "Content-Type": "application/json"
    }
    payload = {"text": message}
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info("Mensaje enviado a Bluesky correctamente.")
        elif response.status_code == 401 and response.json().get("error") == "ExpiredToken":
            logger.warning("Token expirado al enviar mensaje a Bluesky, renovando...")
            if refresh_bluesky_token():
                # Reintentar el envío
                headers["Authorization"] = f"Bearer {current_bluesky_token}"
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    logger.info("Mensaje enviado a Bluesky tras renovación.")
                else:
                    logger.error("Error tras renovación: %s %s", response.status_code, response.text)
            else:
                logger.error("No se pudo renovar el token de Bluesky.")
        else:
            logger.error("Error enviando mensaje a Bluesky: %s %s", response.status_code, response.text)
    except Exception as e:
        logger.error("Excepción al enviar mensaje a Bluesky: %s", e)

# --- Función para la programación de próximos partidos (se mantiene, pero se puede omitir si no se desea) ---
def send_next_match(context: CallbackContext):
    # En este ejemplo, se omite la funcionalidad de próximos partidos.
    pass

# --- Función principal ---
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
    # Programa el envío del próximo partido cada 4 horas (actualmente deshabilitado)
    updater.job_queue.run_repeating(send_next_match, interval=14400, first=30)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
