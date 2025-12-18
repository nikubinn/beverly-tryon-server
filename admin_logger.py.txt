import os
import requests
from threading import Thread

ADMIN_BOT_TOKEN = os.getenv(7946386555:AAHUKXT19phsf90vuWGcGDPEh83WZjty690, "")
ADMIN_CHAT_ID = os.getenv(-1003509322194, "")
ADMIN_LOG_ENABLED = os.getenv("ADMIN_LOG_ENABLED", 1) == "1"

def _api(method):
    return f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/{method}"

def _send(text=None, image_path=None):
    if not ADMIN_LOG_ENABLED or not ADMIN_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        if image_path:
            with open(image_path, "rb") as f:
                requests.post(
                    _api("sendPhoto"),
                    data={"chat_id": ADMIN_CHAT_ID, "caption": text or ""},
                    files={"photo": f},
                    timeout=20
                )
        else:
            requests.post(
                _api("sendMessage"),
                data={"chat_id": ADMIN_CHAT_ID, "text": text or ""},
                timeout=20
            )
    except Exception:
        pass

def send_to_admin_async(text=None, image_path=None):
    Thread(target=_send, kwargs={"text": text, "image_path": image_path}, daemon=True).start()
