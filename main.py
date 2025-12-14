import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# Paths & config
# =========================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
CATALOG_PATH = ASSETS_DIR / "catalog.json"
LOGO_PATH = ASSETS_DIR / "logo.png"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("beverly-tryon-bot")

# user_data keys
K_USER_PHOTO = "user_photo_path"
K_TSHIRT = "sel_tshirt"
K_COLOR = "sel_color"
K_PRINT = "sel_print"

# callback prefixes
CB_TSHIRT = "tshirt:"
CB_COLOR = "color:"
CB_PRINT = "print:"
CB_RESTART = "restart"


# =========================
# Helpers
# =========================
def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog.json not found at: {CATALOG_PATH}")
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_keyboard(items, prefix: str, row: int = 2, extra_buttons=None):
    buttons = []
    for i, it in enumerate(items):
        buttons.append(InlineKeyboardButton(text=str(it), callback_data=f"{prefix}{it}"))
    # chunk into rows
    keyboard = [buttons[i : i + row] for i in range(0, len(buttons), row)]
    if extra_buttons:
        keyboard += extra_buttons
    return InlineKeyboardMarkup(keyboard)


def add_logo_overlay(
    input_path: Path,
    output_path: Path,
    logo_path: Path,
    scale: float = 0.18,
    margin: float = 0.04,
    opacity: float = 0.90,
):
    base = Image.open(input_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    bw, bh = base.size
    target_w = max(1, int(bw * scale))
    ratio = target_w / logo.size[0]
    target_h = max(1, int(logo.size[1] * ratio))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    if opacity < 1.0:
        alpha = logo.split()[-1]
        alpha = alpha.point(lambda p: int(p * opacity))
        logo.putalpha(alpha)

    mx = int(bw * margin)
    my = int(bh * margin)

    # bottom-right
    x = bw - logo.size[0] - mx
    y = bh - logo.size[1] - my

    out = Image.new("RGBA", base.size)
    out.paste(base, (0, 0))
    out.paste(logo, (x, y), logo)
    out.convert("RGB").save(output_path, quality=95)


def get_selection_paths(catalog: Dict[str, Any], tshirt: str, color: str, pr: str) -> Path:
    # catalog: tshirt -> color -> print -> relative path
    rel = catalog[tshirt][color][pr]
    return BASE_DIR / rel  # rel already like "assets/..."
    

def reset_flow(context: ContextTypes.DEFAULT_TYPE):
    for k in (K_TSHIRT, K_COLOR, K_PRINT):
        context.user_data.pop(k, None)


# =========================
# Bot flow
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_flow(context)
    await update.message.reply_text(
        "Привет! Пришли своё фото (одно), и я покажу выбор: футболка → цвет → принт."
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return

    # Save user photo to temp file
    photo = update.message.photo[-1]
    file = await photo.get_file()

    tmp_dir = Path(tempfile.gettempdir())
    user_path = tmp_dir / f"beverly_user_{update.effective_user.id}.jpg"
    await file.download_to_drive(custom_path=str(user_path))

    context.user_data[K_USER_PHOTO] = str(user_path)
    reset_flow(context)

    catalog = context.bot_data["catalog"]
    tshirts = sorted(list(catalog.keys()))

    kb = build_keyboard(
        tshirts,
        CB_TSHIRT,
        row=2,
        extra_buttons=[[InlineKeyboardButton("↻ заново", callback_data=CB_RESTART)]],
    )
    await update.message.reply_text("Фото принято ✅\nВыбери футболку:", reply_markup=kb)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    catalog = context.bot_data["catalog"]

    # restart
    if data == CB_RESTART:
        reset_flow(context)
        tshirts = sorted(list(catalog.keys()))
        kb = build_keyboard(
            tshirts,
            CB_TSHIRT,
            row=2,
            extra_buttons=[[InlineKeyboardButton("↻ заново", callback_data=CB_RESTART)]],
        )
        await query.edit_message_text("Ок, заново. Выбери футболку:", reply_markup=kb)
        return

    # Ensure photo exists
    user_photo = context.user_data.get(K_USER_PHOTO)
    if not user_photo:
        await query.edit_message_text("Сначала пришли фото 📸")
        return

    # Step 1: tshirt
    if data.startswith(CB_TSHIRT):
        tshirt = data[len(CB_TSHIRT):]
        if tshirt not in catalog:
            await query.edit_message_text("Не понял выбор футболки. Попробуй ещё раз.")
            return

        context.user_data[K_TSHIRT] = tshirt
        context.user_data.pop(K_COLOR, None)
        context.user_data.pop(K_PRINT, None)

        colors = sorted(list(catalog[tshirt].keys()))
        kb = build_keyboard(
            colors,
            CB_COLOR,
            row=2,
            extra_buttons=[[InlineKeyboardButton("↻ заново", callback_data=CB_RESTART)]],
        )
        await query.edit_message_text(f"Футболка: {tshirt}\nВыбери цвет:", reply_markup=kb)
        return

    # Step 2: color
    if data.startswith(CB_COLOR):
        color = data[len(CB_COLOR):]
        tshirt = context.user_data.get(K_TSHIRT)
        if not tshirt:
            await query.edit_message_text("Сначала выбери футболку.")
            return
        if color not in catalog[tshirt]:
            await query.edit_message_text("Не понял цвет. Попробуй ещё раз.")
            return

        context.user_data[K_COLOR] = color
        context.user_data.pop(K_PRINT, None)

        prints = sorted(list(catalog[tshirt][color].keys()))
        kb = build_keyboard(
            prints,
            CB_PRINT,
            row=2,
            extra_buttons=[[InlineKeyboardButton("↻ заново", callback_data=CB_RESTART)]],
        )
        await query.edit_message_text(f"Футболка: {tshirt}\nЦвет: {color}\nВыбери принт:", reply_markup=kb)
        return

    # Step 3: print -> generate -> watermark -> send
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

        # Resolve asset path
        asset_path = get_selection_paths(catalog, tshirt, color, pr)
        if not asset_path.exists():
            await query.edit_message_text(f"Файл ассета не найден: {asset_path}")
            return

        await query.edit_message_text(
            f"Ок ✅\nФутболка: {tshirt}\nЦвет: {color}\nПринт: {pr}\n\nГенерирую…"
        )

        # ==========
        # TODO: Replace this stub with NanoBanana API call
        # Right now we just take user photo as "result"
        # ==========
        user_photo_path = Path(user_photo)

        tmp_dir = Path(tempfile.gettempdir())
        out_raw = tmp_dir / f"beverly_out_{update.effective_user.id}.jpg"
        out_final = tmp_dir / f"beverly_out_{update.effective_user.id}_branded.jpg"

        # stub result: copy user photo to out_raw
        out_raw.write_bytes(user_photo_path.read_bytes())

        # watermark
        if LOGO_PATH.exists():
            add_logo_overlay(out_raw, out_final, LOGO_PATH)
            send_path = out_final
        else:
            send_path = out_raw

        # send result
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(send_path, "rb"),
            caption="Готово ✅ (пока заглушка, дальше подключим NanoBanana).",
        )
        return

    await query.edit_message_text("Неизвестная команда кнопки. Нажми /start и попробуй снова.")


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set in environment variables")

    # Load catalog once at startup
    catalog = load_catalog()
    logger.info("Catalog loaded: %d tshirts", len(catalog))

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.bot_data["catalog"] = catalog

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
