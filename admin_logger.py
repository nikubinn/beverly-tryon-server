import os
import requests
from threading import Thread

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
ADMIN_LOG_ENABLED = os.getenv("ADMIN_LOG_ENABLED", "1").strip() == "1"

def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/{method}"

def _send(text: str | None = None, image_bytes: bytes | None = None, filename: str = "result.jpg"):
    if not ADMIN_LOG_ENABLED:
        return
    if not ADMIN_BOT_TOKEN or not ADMIN_CHAT_ID:
        return

    try:
        if image_bytes is not None:
            requests.post(
                _api("sendPhoto"),
                data={"chat_id": ADMIN_CHAT_ID, "caption": text or ""},
                files={"photo": (filename, image_bytes)},
                timeout=25,
            )
        else:
            requests.post(
                _api("sendMessage"),
                data={"chat_id": ADMIN_CHAT_ID, "text": text or ""},
                timeout=25,
            )
    except Exception:
        # Never break the main bot because of admin logging
        pass

def send_to_admin_async(text: str | None = None, image_bytes: bytes | None = None, filename: str = "result.jpg"):
    Thread(target=_send, kwargs={"text": text, "image_bytes": image_bytes, "filename": filename}, daemon=True).start()
