import json
import logging
import os
import tempfile
import time
import atexit
import fcntl
import asyncio
from pathlib import Path
from typing import Any, Dict, Tuple
from collections import defaultdict
import datetime
from zoneinfo import ZoneInfo

import redis


from PIL import Image, ImageOps  # ✅ EXIF normalize

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Gemini SDK
from google import genai
from google.genai import types

# Prompt blocks
from prompts import GLOBAL_CONSTRAINTS, GLOBAL_QUALITY, PRODUCT_PROMPTS

# ✅ ADMIN LOGGER
from admin_logger import send_to_admin_async


# =========================
# SINGLE INSTANCE LOCK
# =========================
_lock_fh = None

def acquire_single_instance_lock():
    """
    На Render (webhook) это обычно не нужно, но оставляем как есть.
    Если вдруг будет второй процесс — мы его зарежем.
    """
    global _lock_fh
    _lock_fh = open("/tmp/telegram_polling.lock", "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another Telegram bot instance is already running")
    atexit.register(lambda: _lock_fh.close())


# =========================
# PER-USER GENERATION LOCKS
# =========================
USER_LOCKS: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


# =========================
# PATHS & CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
CATALOG_PATH = ASSETS_DIR / "catalog.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview").strip()

# =========================
# RATE LIMIT (Redis)
# =========================
REDIS_URL = os.getenv("REDIS_URL", "").strip()
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "4"))
LIMIT_TZ = os.getenv("LIMIT_TZ", "Europe/Minsk").strip()  # 00:00–23:59 by this TZ


IMAGE_SIZE_POLICY = "2K"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("beverly-tryon-bot")

# метка сборки — чтобы понимать, что задеплоилось
BUILD_MARKER = "v4a-webhook-admin-bytes-2025-12-19-aspect-off-lock-exif-uniquephoto"

# =========================
# Redis client + daily limiter
# =========================
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        _redis_client = None
        return None
    try:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable (%s). Falling back to in-memory limiter.", e)
        _redis_client = None
        return None

# in-memory fallback (resets on restart)
_mem_counts = {}
_mem_datestr = None

def _now_tz():
    try:
        tz = ZoneInfo(LIMIT_TZ or "Europe/Minsk")
    except Exception:
        tz = ZoneInfo("Europe/Minsk")
    return datetime.datetime.now(tz)

def _today_str():
    return _now_tz().strftime("%Y%m%d")

def _seconds_until_end_of_day():
    now = _now_tz()
    tomorrow = now.date() + datetime.timedelta(days=1)
    end = datetime.datetime.combine(tomorrow, datetime.time(0, 0, 0), tzinfo=now.tzinfo)
    delta = end - now
    return max(1, int(delta.total_seconds()))

def consume_daily_quota(user_id: int) -> Tuple[bool, int, int]:
    """Returns (allowed, remaining, used_today) for daily window in LIMIT_TZ."""
    datestr = _today_str()
    r = _get_redis()
    key = f"tryon:daily:{user_id}:{datestr}"

    if r is None:
        global _mem_datestr
        if _mem_datestr != datestr:
            _mem_counts.clear()
            _mem_datestr = datestr
        used = _mem_counts.get(key, 0) + 1
        _mem_counts[key] = used
        allowed = used <= DAILY_LIMIT
        remaining = max(0, DAILY_LIMIT - used)
        return allowed, remaining, used

    used = int(r.incr(key))
    if used == 1:
        r.expire(key, _seconds_until_end_of_day())
    allowed = used <= DAILY_LIMIT
    remaining = max(0, DAILY_LIMIT - used)
    return allowed, remaining, used

def refund_daily_quota(user_id: int):
    """Refund one quota unit if generation failed."""
    datestr = _today_str()
    r = _get_redis()
    key = f"tryon:daily:{user_id}:{datestr}"

    if r is None:
        if key in _mem_counts and _mem_counts[key] > 0:
            _mem_counts[key] -= 1
        return

    try:
        r.decr(key)
    except Exception:
        pass

# =========================
# UI LABELS / DISPLAY MAPS
# =========================
# Buttons (short) — WITHOUT "T-SHIRT" to fit
TSHIRT_BUTTON_LABELS = {
    "alien_drip_t_shirt": "[ ALIEN DRIP ]",
    "moon_walk_t_shirt": "[ MOON WALK ]",
    "pink_swaga_t_shirt": "[ PINK SWAGA ]",
    "pocket_t_shirt": "[ POCKET ]",
}

# Result (full) — keep full names
TSHIRT_RESULT_LABELS = {
    "alien_drip_t_shirt": "[ ALIEN DRIP T-SHIRT ]",
    "moon_walk_t_shirt": "[ MOON WALK T-SHIRT ]",
    "pink_swaga_t_shirt": "[ PINK SWAGA T-SHIRT ]",
    "pocket_t_shirt": "[ POCKET T-SHIRT ]",
}

COLOR_LABELS = {
    "black": "[ BLACK ]",
    "pink": "[ PINK ]",
    "white": "[ WHITE ]",
}

RESTART_LABEL = "[ ↻ ЗАНОВО ]"

TEXT_PHOTO_OK = "ага\n[ ВЫБЕРИ ФУТБОЛКУ ]"
TEXT_PICK_COLOR = "[ ВЫБЕРИ ЦВЕТ ]"
TEXT_PICK_PRINT = "[ ВЫБЕРИ ПРИНТ ]"
TEXT_TRYON = "идёт примерка 👽"
TEXT_DONE = "готово 🦇"


# =========================
# STATE KEYS
# =========================
K_USER_PHOTO = "user_photo_path"
K_TSHIRT = "sel_tshirt"
K_COLOR = "sel_color"
K_PRINT = "sel_print"

CB_TSHIRT = "tshirt:"
CB_COLOR = "color:"
CB_PRINT = "print:"
CB_RESTART = "restart"


# =========================
# HELPERS
# =========================
def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog.json not found: {CATALOG_PATH}")
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_keyboard(items, prefix: str, row: int = 2, label_map=None, extra_buttons=None):
    label_map = label_map or {}
    buttons = [
        InlineKeyboardButton(text=label_map.get(str(it), str(it)), callback_data=f"{prefix}{it}")
        for it in items
    ]
    keyboard = [buttons[i:i + row] for i in range(0, len(buttons), row)]
    if extra_buttons:
        keyboard += extra_buttons
    return InlineKeyboardMarkup(keyboard)


def reset_flow(context: ContextTypes.DEFAULT_TYPE):
    for k in (K_TSHIRT, K_COLOR, K_PRINT):
        context.user_data.pop(k, None)


def _mime_for_path(p: Path) -> str:
    return "image/png" if p.suffix.lower() == ".png" else "image/jpeg"


def _part_from_path(p: Path) -> types.Part:
    return types.Part.from_bytes(
        data=p.read_bytes(),
        mime_type=_mime_for_path(p),
    )


def _label_print(pr: str) -> str:
    return f"[ {str(pr).replace('_', ' ').upper()} ]"


def _label_color(c: str) -> str:
    return COLOR_LABELS.get(c, f"[ {str(c).replace('_', ' ').upper()} ]")


def _label_tshirt_button(t: str) -> str:
    return TSHIRT_BUTTON_LABELS.get(t, f"[ {str(t).replace('_', ' ').upper()} ]")


def _label_tshirt_result(t: str) -> str:
    return TSHIRT_RESULT_LABELS.get(t, f"[ {str(t).replace('_', ' ').upper()} ]")


# =========================
# PROMPT BUILDER (NO ASPECT CONSTRAINTS)
# =========================
def build_tryon_prompt(tshirt: str, color: str, pr: str) -> str:
    product = PRODUCT_PROMPTS.get(tshirt, {})

    color_l = str(color).lower()
    pink_lock = ""
    if "pink" in color_l:
        pink_lock = """
PINK COLOR LOCK (CRITICAL):
- The garment fabric MUST remain clearly PINK.
- Never output white, off-white, beige, gray, or any neutral color instead of pink.
- Do NOT neutralize, desaturate, or wash out pink under any lighting.
- If you are unsure, prefer pink (not white).
""".strip()

    return f"""
This is an image EDIT task, not image generation.

You will edit the FIRST image (the person photo).

MULTI-IMAGE RULE (CRITICAL):
- Edit ONLY the FIRST image.
- The LAST image is provided ONLY to lock canvas size and aspect ratio.
- Do NOT copy content from the last image.

PRIMARY TASK:
- Replace ONLY the T-shirt on the person using the SECOND image as the exact reference.
- Match color, print placement, scale, and orientation exactly.
- Keep everything else unchanged.

REFERENCE PRIORITY (CRITICAL):
- The SECOND image (garment reference) is the single source of truth for fabric color, print colors, texture, and pattern.
- Match garment color by visual sampling from the reference image.
- Do NOT reinterpret the garment color based on the person photo or scene lighting.
- If anything conflicts, the garment reference image ALWAYS wins.

{pink_lock}

FRAMING & CANVAS (STRICT):
- Preserve the EXACT original canvas of the first image.
- The output image MUST have the same width, height, and aspect ratio as the first image.
- Do NOT crop, zoom, rotate, or reframe the image.
- Do NOT change camera position or field of view.
- Keep the person fully visible exactly as in the first image (head, hands, legs, shoes).
- The original image content must remain pixel-aligned in the same position.

{GLOBAL_CONSTRAINTS}
{GLOBAL_QUALITY}

GARMENT SPEC:
{product.get("garment_dna", "")}

PLACEMENT SPEC:
{product.get("placement_dna", "")}

COLOR SPEC:
{product.get("colors", {}).get(color, "")}

PRINT SPEC:
{product.get("prints", {}).get(pr, "")}

OUTPUT:
- Generate ONE image.
- Output MUST have exactly the same pixel dimensions and aspect ratio as the first image.
- 2K class output is OK, but DO NOT change the original canvas framing.
""".strip()


# =========================
# GEMINI SYNC GENERATION
# =========================
def gemini_tryon_sync(
    user_photo: Path,
    asset_path: Path,
    tshirt: str,
    color: str,
    pr: str,
) -> Tuple[bytes, str]:

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = build_tryon_prompt(tshirt, color, pr)

    parts = [
        prompt,
        _part_from_path(user_photo),   # TARGET: edit this image
        _part_from_path(asset_path),   # REFERENCE: garment
        _part_from_path(user_photo),   # ANCHOR: lock canvas/aspect
    ]

    logger.info("Gemini START | model=%s", GEMINI_MODEL)
    t0 = time.time()

    # ✅ ВАЖНО: не передаем aspect_ratio
    cfg = types.GenerateContentConfig(
        image_config=types.ImageConfig(
            image_size=IMAGE_SIZE_POLICY,  # "2K"
        )
    )

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=parts, config=cfg)
    logger.info("Gemini END | %.2fs", time.time() - t0)

    cand = resp.candidates[0]
    for part in cand.content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            return inline.data, GEMINI_MODEL

    raise RuntimeError("Gemini returned no image data")


# =========================
# BOT HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_flow(context)
    await update.message.reply_text("Пришли фото 📸")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()

    tmp = Path(tempfile.gettempdir())

    # ✅ Unique filename per upload (prevents overwriting and cross-run mixing)
    u = update.effective_user
    mid = update.message.message_id
    user_path = tmp / f"user_{u.id}_{mid}.jpg"

    await file.download_to_drive(custom_path=str(user_path))

    # ✅ Normalize EXIF orientation (fixes random portrait/landscape issues)
    try:
        with Image.open(user_path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.save(user_path, format="JPEG", quality=95)
    except Exception:
        pass

    context.user_data[K_USER_PHOTO] = str(user_path)
    reset_flow(context)

    catalog = context.bot_data["catalog"]
    tshirts = sorted(catalog.keys())

    kb = build_keyboard(
        tshirts,
        CB_TSHIRT,
        label_map={k: _label_tshirt_button(k) for k in tshirts},
        extra_buttons=[[InlineKeyboardButton(RESTART_LABEL, callback_data=CB_RESTART)]],
    )

    await update.message.reply_text(TEXT_PHOTO_OK, reply_markup=kb)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    catalog = context.bot_data["catalog"]

    if data == CB_RESTART:
        reset_flow(context)
        tshirts = sorted(catalog.keys())
        kb = build_keyboard(
            tshirts,
            CB_TSHIRT,
            label_map={k: _label_tshirt_button(k) for k in tshirts},
            extra_buttons=[[InlineKeyboardButton(RESTART_LABEL, callback_data=CB_RESTART)]],
        )
        await query.edit_message_text(TEXT_PHOTO_OK, reply_markup=kb)
        return

    user_photo = context.user_data.get(K_USER_PHOTO)
    if not user_photo:
        await query.edit_message_text("Сначала пришли фото 📸")
        return

    if data.startswith(CB_TSHIRT):
        tshirt = data[len(CB_TSHIRT):]
        if tshirt not in catalog:
            await query.edit_message_text("Не понял выбор. Нажми /start и попробуй снова.")
            return

        context.user_data[K_TSHIRT] = tshirt
        colors = sorted(catalog[tshirt].keys())

        kb = build_keyboard(
            colors,
            CB_COLOR,
            label_map={c: _label_color(c) for c in colors},
            row=2,
        )
        await query.edit_message_text(TEXT_PICK_COLOR, reply_markup=kb)
        return

    if data.startswith(CB_COLOR):
        color = data[len(CB_COLOR):]
        tshirt = context.user_data.get(K_TSHIRT)
        if not tshirt or color not in catalog.get(tshirt, {}):
            await query.edit_message_text("Сначала выбери футболку, затем цвет.")
            return

        context.user_data[K_COLOR] = color
        prints = sorted(catalog[tshirt][color].keys())

        kb = build_keyboard(
            prints,
            CB_PRINT,
            label_map={p: _label_print(p) for p in prints},
            row=2,
        )
        await query.edit_message_text(TEXT_PICK_PRINT, reply_markup=kb)
        return

    if data.startswith(CB_PRINT):
        pr = data[len(CB_PRINT):]
        tshirt = context.user_data.get(K_TSHIRT)
        color = context.user_data.get(K_COLOR)

        if not tshirt or not color:
            await query.edit_message_text("Сначала выбери футболку и цвет.")
            return
        if pr not in catalog[tshirt][color]:
            await query.edit_message_text("Не понял принт. Попробуй ещё раз.")
            return

        context.user_data[K_PRINT] = pr

        # ✅ daily limit (00:00–23:59 by LIMIT_TZ, default Europe/Minsk)
        allowed, remaining, used_today = consume_daily_quota(update.effective_user.id)
        if not allowed:
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton(RESTART_LABEL, callback_data=CB_RESTART)]]
            )
            await query.edit_message_text(
                f"Лимит на сегодня исчерпан: {min(used_today, DAILY_LIMIT)}/{DAILY_LIMIT}.\n"
                f"Попробуй снова завтра (по времени {LIMIT_TZ}).",
                reply_markup=kb,
            )
            return

        await query.edit_message_text(TEXT_TRYON)

        asset_path = BASE_DIR / catalog[tshirt][color][pr]
        logger.info(
            "Selected | user=%s (@%s) | tshirt=%s | color=%s | print=%s | asset=%s",
            update.effective_user.id,
            update.effective_user.username,
            tshirt,
            color,
            pr,
            asset_path,
        )
        user_photo_path = Path(user_photo)

        # ✅ lock per user to prevent overlapping generations / cross-mix
        lock = USER_LOCKS[update.effective_user.id]
        async with lock:
            try:
                loop = asyncio.get_running_loop()
                out_bytes, _model_used = await loop.run_in_executor(
                    None,
                    lambda: gemini_tryon_sync(
                        user_photo=user_photo_path,
                        asset_path=asset_path,
                        tshirt=tshirt,
                        color=color,
                        pr=pr,
                    )
                )

                # ✅ Hard-enforce output canvas to match the ORIGINAL user photo (prevents random landscape/portrait flips)
                try:
                    with Image.open(user_photo_path) as _in_im:
                        _target_size = _in_im.size  # (W, H)
                    from io import BytesIO
                    with Image.open(BytesIO(out_bytes)) as _out_im:
                        _out_im = _out_im.convert("RGB")
                        if _out_im.size != _target_size:
                            _out_im = ImageOps.fit(_out_im, _target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                            buf = BytesIO()
                            _out_im.save(buf, format="JPEG", quality=95)
                            out_bytes = buf.getvalue()
                except Exception:
                    pass


                caption = (
                    f"{TEXT_DONE}\n"
                    f"{_label_tshirt_result(tshirt)}\n"
                    f"{_label_color(color)}\n"
                    f"{_label_print(pr)}"
                
                    f"\n[ осталось сегодня: {remaining}/{DAILY_LIMIT} ]"
                )

                # Send to user (bytes напрямую)
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=out_bytes,
                    caption=caption,
                )

                # ✅ Send to admin logger chat (same image + metadata) — image_bytes
                u = update.effective_user
                uname = (u.username or "").strip()
                uname_display = f"@{uname}" if uname else "(no username)"

                send_to_admin_async(
                    text=(
                        "🧪 TRY-ON RESULT\n"
                        f"user_id: {u.id}\n"
                        f"username: {uname_display}\n"
                        f"товар: {_label_tshirt_result(tshirt)}\n"
                        f"размер: -\n"
                        f"цвет: {_label_color(color)}\n"
                        f"принт: {_label_print(pr)}"
                    ),
                    image_bytes=out_bytes,
                    filename="result.jpg",
                )

            except Exception as e:
                refund_daily_quota(update.effective_user.id)
                logger.exception("Generation failed")
                send_to_admin_async(
                    text=(
                        f"GEN ERROR | @{update.effective_user.username or 'no_username'} | id={update.effective_user.id}\n"
                        f"tshirt={tshirt} color={color} print={pr}\n"
                        f"{e}"
                    )
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Ошибка генерации: {e}",
                )
            return

    await query.edit_message_text("Неизвестная команда. Нажми /start и попробуй снова.")


# =========================
# MAIN (WEBHOOK)
# =========================
def main():
    acquire_single_instance_lock()

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN missing")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing")

    # Render прокидывает URL и PORT в Web Service
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    port = int(os.getenv("PORT", "10000"))

    if not render_url:
        raise RuntimeError("RENDER_EXTERNAL_URL missing (Render Web Service expected)")

    webhook_path = f"/webhook/{TELEGRAM_TOKEN}"
    webhook_url = f"{render_url}{webhook_path}"

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.bot_data["catalog"] = load_catalog()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Bot started (webhook) | BUILD=%s", BUILD_MARKER)
    logger.info("Gemini model=%s | policy=%s", GEMINI_MODEL, IMAGE_SIZE_POLICY)
    logger.info("Webhook URL=%s", webhook_url)

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path.lstrip("/"),
        webhook_url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
