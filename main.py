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

from PIL import Image

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
    global _lock_fh
    _lock_fh = open("/tmp/telegram_polling.lock", "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another Telegram bot instance is already running")
    atexit.register(lambda: _lock_fh.close())


# =========================
# PATHS & CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
CATALOG_PATH = ASSETS_DIR / "catalog.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview").strip()

IMAGE_SIZE_POLICY = "2K"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("beverly-tryon-bot")
BUILD_MARKER = "v4a-admin-bytes-2025-12-19"


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



def _pick_aspect_ratio_for_user_photo(user_photo: Path) -> str:
    """Return a supported aspect ratio string based on the user's photo orientation."""
    try:
        with Image.open(user_photo) as im:
            w, h = im.size
    except Exception:
        return ""

    # Square-ish
    if w > 0 and h > 0 and abs(w - h) / max(w, h) < 0.08:
        return "1:1"

    return "9:16" if h > w else "16:9"


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
    aspect = _pick_aspect_ratio_for_user_photo(user_photo)
    logger.info("Gemini aspect hint=%s (from user photo)", aspect if aspect else "none")

    try:
        cfg = types.GenerateContentConfig(
            image_config=types.ImageConfig(
                aspect_ratio=aspect if aspect else None,
                image_size=IMAGE_SIZE_POLICY,
            )
        )
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=parts, config=cfg)
        logger.info("Gemini config applied (aspect hint)")
    except Exception as e:
        logger.warning("Gemini config NOT applied, fallback to default generate_content(): %s", e)
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=parts)
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
    user_path = tmp / f"user_{update.effective_user.id}.jpg"
    await file.download_to_drive(custom_path=str(user_path))

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
        await query.edit_message_text(TEXT_TRYON)

        asset_path = BASE_DIR / catalog[tshirt][color][pr]
        logger.info("Selected | user=%s (@%s) | tshirt=%s | color=%s | print=%s | asset=%s", update.effective_user.id, update.effective_user.username, tshirt, color, pr, asset_path)
        user_photo_path = Path(user_photo)

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

            caption = (
                f"{TEXT_DONE}\n"
                f"{_label_tshirt_result(tshirt)}\n"
                f"{_label_color(color)}\n"
                f"{_label_print(pr)}"
            )

            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                f.write(out_bytes)
                f.flush()

                # Send to user
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f.name,
                    caption=caption,
                )

                # ✅ Send to admin logger chat (same image + metadata)
                u = update.effective_user
                uname = (u.username or "").strip()
                uname_display = f"@{uname}" if uname else "(no username)"

                # ✅ FIX: send bytes directly (no image_path)
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
# MAIN
# =========================
def main():
    acquire_single_instance_lock()

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN missing")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.bot_data["catalog"] = load_catalog()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Bot started (polling) | BUILD=%s", BUILD_MARKER)
    logger.info("Gemini model=%s | policy=%s", GEMINI_MODEL, IMAGE_SIZE_POLICY)

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
