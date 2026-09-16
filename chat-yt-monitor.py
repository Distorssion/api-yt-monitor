

import os
import time
import requests

#config
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
VIDEO_ID = os.environ.get("VIDEO_ID", "")          # el que aparece en ?v=XXXXXXX de la URL
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Palabras clave a buscar, separadas por coma en la variable KEYWORDS
KEYWORDS = os.environ.get(
    "KEYWORDS", "forms,gle,forms.gle,short,docs,google"
).split(",")

#intervalo
MIN_POLL_INTERVAL_SECONDS = 30

# ============================================================
# LÓGICA DEL SCRIPT — normalmente no necesitas tocar nada de aquí abajo
# ============================================================

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def get_live_chat_id(video_id: str, api_key: str) -> str:
    """Obtiene el liveChatId asociado a un video en vivo."""
    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "liveStreamingDetails",
        "id": video_id,
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        raise RuntimeError(
            "No se encontró el video. Revisa que el VIDEO_ID sea correcto "
            "y que la transmisión esté en vivo."
        )

    details = items[0].get("liveStreamingDetails", {})
    live_chat_id = details.get("activeLiveChatId")

    if not live_chat_id:
        raise RuntimeError(
            "Este video no tiene un chat en vivo activo. "
            "¿La transmisión ya empezó? ¿El chat está habilitado?"
        )

    return live_chat_id


def send_to_discord(webhook_url: str, author: str, message: str, matched_keyword: str) -> None:
    """Envía un mensaje formateado al canal de Discord vía webhook."""
    payload = {
        "content": (
            f"🔔 **Palabra clave detectada:** `{matched_keyword}`\n"
            f"**{author}:** {message}"
        )
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code not in (200, 204):
        print(f"[!] Error enviando a Discord ({resp.status_code}): {resp.text}")


def contains_keyword(text: str, keywords: list[str]) -> str | None:
    """Devuelve la primera palabra clave encontrada en el texto, o None."""
    lowered = text.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            return kw
    return None


def monitor_chat(video_id: str, api_key: str, webhook_url: str, keywords: list[str]) -> None:
    live_chat_id = get_live_chat_id(video_id, api_key)
    print(f"[+] Chat en vivo encontrado. liveChatId = {live_chat_id}")
    print(f"[+] Buscando palabras clave: {keywords}")

    page_token = None
    seen_message_ids = set()

    while True:
        params = {
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = requests.get(
                f"{YOUTUBE_API_BASE}/liveChat/messages", params=params, timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[!] Error consultando el chat: {e}. Reintentando en 10s...")
            time.sleep(10)
            continue

        for item in data.get("items", []):
            msg_id = item.get("id")
            if msg_id in seen_message_ids:
                continue
            seen_message_ids.add(msg_id)

            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {}).get("displayName", "Desconocido")
            text = snippet.get("displayMessage", "")

            matched = contains_keyword(text, keywords)
            if matched:
                print(f"[MATCH] ({matched}) {author}: {text}")
                send_to_discord(webhook_url, author, text, matched)

        page_token = data.get("nextPageToken")

        # YouTube indica el intervalo mínimo recomendado de consulta
        suggested_interval = data.get("pollingIntervalMillis", 5000) / 1000
        wait_time = max(suggested_interval, MIN_POLL_INTERVAL_SECONDS)
        time.sleep(wait_time)


if __name__ == "__main__":
    missing = [
        name
        for name, val in [
            ("YOUTUBE_API_KEY", YOUTUBE_API_KEY),
            ("VIDEO_ID", VIDEO_ID),
            ("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL),
        ]
        if not val
    ]
    if missing:
        raise SystemExit(
            f"[!] Faltan variables de entorno: {', '.join(missing)}. "
            "Configúralas en el panel de tu servicio de hosting."
        )

    try:
        monitor_chat(VIDEO_ID, YOUTUBE_API_KEY, DISCORD_WEBHOOK_URL, KEYWORDS)
    except KeyboardInterrupt:
        print("\n[+] Monitoreo detenido por el usuario.")
    except RuntimeError as e:
        print(f"[!] {e}")
