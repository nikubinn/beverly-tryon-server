import json
import logging
import os
import tempfile
import time
import atexit
import fcntl
import asyncio
import io
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


# =====================================================
# SINGLE INSTANCE LOCK (prevents double polling)
# =====================================================
_lock_fh = None

def acquire_single_instance_lock():
    global _lock_fh
    _lock_fh = open("/tmp/telegram_polling.lock", "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another Telegram bot instance is already running")
    atexit.register(lambda: _lock_fh.close())


# =====================================================
# PATHS & CONFIG
# =====================================================
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


# =====================================================
# STATE KEYS
# =====================================================
K_USER_PHOTO = "user_photo_path"
K_ORIG_SIZE = "orig_size"
K_TSHIRT = "sel_tshirt"
K_COLOR = "sel_color"
K_PRINT = "sel_print"

CB_TSHIRT = "tshirt:"
CB_COLOR = "color:"
CB_PRINT = "print:"
CB_RESTART = "restart"


# =====================================================
# HELPERS
# =====================================================
def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog.json not found: {CATALOG_PATH}")
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_keyboard(items, prefix: str, row: int = 2, extra_buttons=None):
    buttons = [
        InlineKeyboardButton(text=str(it), callback_data=f"{prefix}{it}")
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


# =====================================================
# ASPECT RATIO PRESERVATION (LETTERBOX)
# =====================================================
def preserve_aspect_ratio(img: Image.Image, target_size: tuple[int, int], bg=(0, 0, 0)):
    target_w, target_h = target_size
    src_w, src_h = img.size

    scale = min(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), bg)
    canvas.paste(
        img,
        ((target_w - new_w) // 2, (target_h - new_h) // 2)
    )
    return canvas


# =====================================================
# PROMPT BUILDER (NO LOGO)
# =====================================================
def build_tryon_prompt(tshirt: str, color: str, pr: str) -> str:
    product = PRODUCT_PROMPTS.get(tshirt, {})
    return f"""
You will edit the FIRST image (the person photo).

PRIMARY TASK:
- Replace ONLY the T-shirt on the person using the SECOND image as reference.
- Match color, print placement, scale, and orientation exactly.
- Keep everything else unchanged.

STRICT FRAMING RULE:
- Preserve original camera framing and aspect ratio.
- Do NOT crop, zoom, square, or reframe.

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
- Generate ONE image
- ~2048px longest side (2K)
""".strip()


# =====================================================
# GEMINI GENERATION (SYNC)
# =====================================================
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
        _part_from_path(user_photo),
        _part_from_path(asset_path),
    ]

    logger.info("Gemini START | model=%s", GEMINI_MODEL)
    t0 = time.time()
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=parts)
    logger.info("Gemini END | %.2fs", time.time() - t0)

    cand = resp.candidates[0]
    for part in cand.content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            return inline.data, GEMINI_MODEL

    raise RuntimeError("Gemini returned no image data")


# =====================================================
# BOT HANDLERS
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_flow(context)
    await update.message.reply_text("Пришли фото — выберем футболку 👕")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()

    tmp = Path(tempfile.gettempdir())
    user_path = tmp / f"user_{update.effective_user.id}.jpg"
    await file.download_to_drive(custom_path=str(user_path))

    img = Image.open(user_path)
    context.user_data[K_ORIG_SIZE] = img.size
    context.user_data[K_USER_PHOTO] = str(user_path)

    reset_flow(context)

    catalog = context.bot_data["catalog"]
    kb = build_keyboard(
        sorted(catalog.keys()),
        CB_TSHIRT,
        extra_buttons=[[InlineKeyboardButton("↻ заново", callback_data=CB_RESTART)]],
    )
    await update.message.reply_text("Фото принято ✅\nВыбери футболку:", reply_markup=kb)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    catalog = context.bot_data["catalog"]

    if data == CB_RESTART:
        reset_flow(context)
        kb = build_keyboard(sorted(catalog.keys()), CB_TSHIRT)
        await query.edit_message_text("Заново. Выбери футболку:", reply_markup=kb)
        return

    user_photo = context.user_data.get(K_USER_PHOTO)
    if not user_photo:
        await query.edit_message_text("Сначала пришли фото 📸")
        return

    if data.startswith(CB_TSHIRT):
        context.user_data[K_TSHIRT] = data[len(CB_TSHIRT):]
        kb = build_keyboard(sorted(catalog[context.user_data[K_TSHIRT]].keys()), CB_COLOR)
        await query.edit_message_text("Выбери цвет:", reply_markup=kb)
        return

    if data.startswith(CB_COLOR):
        context.user_data[K_COLOR] = data[len(CB_COLOR):]
        kb = build_keyboard(
            sorted(catalog[context.user_data[K_TSHIRT]][context.user_data[K_COLOR]].keys()),
            CB_PRINT,
        )
        await query.edit_message_text("Выбери принт:", reply_markup=kb)
        return

    if data.startswith(CB_PRINT):
        pr = data[len(CB_PRINT):]
        context.user_data[K_PRINT] = pr

        await query.edit_message_text("Генерирую (2K)…")

        loop = asyncio.get_running_loop()
        out_bytes, model_used = await loop.run_in_executor(
            None,
            lambda: gemini_tryon_sync(
                Path(user_photo),
                BASE_DIR / catalog[context.user_data[K_TSHIRT]][context.user_data[K_COLOR]][pr],
                context.user_data[K_TSHIRT],
                context.user_data[K_COLOR],
                pr,
            ),
        )

        gen_img = Image.open(io.BytesIO(out_bytes)).convert("RGB")
        orig_size = context.user_data.get(K_ORIG_SIZE)
        if orig_size:
            gen_img = preserve_aspect_ratio(gen_img, orig_size)

        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            gen_img.save(f.name, quality=95, subsampling=0)
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=f.name,
                caption=f"Готово ✅ | {model_used} | пропорции сохранены",
            )


# =====================================================
# MAIN
# =====================================================
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

    logger.info("Bot started (polling)")
    logger.info("Gemini model=%s | policy=%s", GEMINI_MODEL, IMAGE_SIZE_POLICY)

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
