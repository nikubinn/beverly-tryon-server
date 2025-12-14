import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

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

# Gemini SDK
from google import genai
from google.genai import types

# Our prompt descriptors (prompts.py рядом с main.py)
from prompts import GLOBAL_CONSTRAINTS, GLOBAL_QUALITY, PRODUCT_PROMPTS

# =========================
# Paths & config
# =========================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
CATALOG_PATH = ASSETS_DIR / "catalog.json"
LOGO_PATH = ASSETS_DIR / "logo.png"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Default: Gemini 3 Pro Image
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip()

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
    for it in items:
        buttons.append(InlineKeyboardButton(text=str(it), callback_data=f"{prefix}{it}"))
    keyboard = [buttons[i : i + row] for i in range(0, len(buttons), row)]
    if extra_buttons:
        keyboard += extra_buttons
    return InlineKeyboardMarkup(keyboard)


def get_selection_paths(catalog: Dict[str, Any], tshirt: str, color: str, pr: str) -> Path:
    rel = catalog[tshirt][color][pr]  # "assets/..."
    return BASE_DIR / rel


def reset_flow(context: ContextTypes.DEFAULT_TYPE):
    for k in (K_TSHIRT, K_COLOR, K_PRINT):
        context.user_data.pop(k, None)


def _mime_for_path(p: Path) -> str:
    ext = p.suffix.lower()
    if ext == ".png":
        return "image/png"
    return "image/jpeg"


def _part_from_file(p: Path) -> types.Part:
    return types.Part.from_bytes(data=p.read_bytes(), mime_type=_mime_for_path(p))


def _part_from_jpeg_bytes(b: bytes) -> types.Part:
    return types.Part.from_bytes(data=b, mime_type="image/jpeg")


def build_tryon_prompt(tshirt: str, color: str, pr: str) -> str:
    """
    Собираем финальный промпт:
    - GLOBAL_CONSTRAINTS + GLOBAL_QUALITY
    - garment_dna + placement_dna + color rule + print rule (из prompts.py)
    - правила про лого-вывеску
    - требование 2K (longest side ~2048) + запрет 4K
    """
    product = PRODUCT_PROMPTS.get(tshirt, {})
    garment_dna = (product.get("garment_dna") or "").strip()
    placement_dna = (product.get("placement_dna") or "").strip()

    colors = product.get("colors", {}) or {}
    prints = product.get("prints", {}) or {}

    color_rule = (colors.get(color) or "").strip()
    print_rule = (prints.get(pr) or "").strip()

    # Лого — в фоне как вывеска (не watermark)
    logo_rules = """
LOGO RULE (THIRD image):
- Place the provided logo ONLY in the background behind the subject as a small physical sign
  (e.g., subtle wall plaque / tiny neon sign).
- Add a violet sheen/glow, subtle and stylish. Slightly out of focus, physically plausible.
- DO NOT put the logo on the T-shirt. DO NOT add any other text or logos.
"""

    # 2K constraint
    out_rules = """
OUTPUT RESOLUTION:
- Generate a single high-quality image.
- Target around 2048 px on the longest side (2K class).
- Do NOT generate 4K or ultra-high resolution.
- Focus detail primarily on the T-shirt and its print, not on the background.
"""

    prompt = f"""
You will edit the FIRST image (the person photo).

PRIMARY TASK:
- Replace ONLY the T-shirt on the person using the SECOND image as the exact visual reference for the shirt/print.
- Match color, print placement, scale, and orientation exactly as in the reference image.
- Keep everything else unchanged.

{GLOBAL_CONSTRAINTS}

{GLOBAL_QUALITY}

GARMENT SPEC:
{garment_dna}

PLACEMENT SPEC:
{placement_dna}

COLOR SPEC:
{color_rule}

PRINT SPEC:
{print_rule}

{logo_rules}

{out_rules}
"""
    return "\n".join([line.rstrip() for line in prompt.strip().splitlines()]).strip()


def gemini_tryon(user_photo_path: Path, asset_path: Path, logo_path: Path, tshirt: str, color: str, pr: str) -> bytes:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in environment variables")

    if not user_photo_path.exists():
        raise FileNotFoundError(f"User photo not found: {user_photo_path}")
    if not asset_path.exists():
        raise FileNotFoundError(f"Asset not found: {asset_path}")
    if not logo_path.exists():
        raise FileNotFoundError(f"Logo not found: {logo_path}")

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = build_tryon_prompt(tshirt, color, pr)

    # 3 images: person + tshirt reference + logo
    person_bytes = user_photo_path.read_bytes()
    person_part = _part_from_jpeg_bytes(person_bytes)
    tshirt_part = _part_from_file(asset_path)
    logo_part = _part_from_file(logo_path)

    resp = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=[prompt, person_part, tshirt_part, logo_part],
    )

    # Extract inline image bytes from response
    out_bytes = None
    cand = resp.candidates[0]
    for part in cand.content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            out_bytes = inline.data
            break

    if not out_bytes:
        raise RuntimeError(
            "Gemini returned no image bytes (text-only response). "
            "Try another model name in GEMINI_IMAGE_MODEL or check account access."
        )

    return out_bytes


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
        await query.edit_message_text(
            f"Футболка: {tshirt}\nЦвет: {color}\nВыбери принт:",
            reply_markup=kb
        )
        return

    # Step 3: print -> generate -> send
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

        asset_path = get_selection_paths(catalog, tshirt, color, pr)
        if not asset_path.exists():
            await query.edit_message_text(f"Файл ассета не найден: {asset_path}")
            return

        if not LOGO_PATH.exists():
            await query.edit_message_text("logo.png не найден в assets/. Добавь logo.png.")
            return

        await query.edit_message_text(
            f"Ок ✅\nФутболка: {tshirt}\nЦвет: {color}\nПринт: {pr}\n\nГенерирую (Gemini 3 Pro Image, 2K)…"
        )

        user_photo_path = Path(user_photo)

        tmp_dir = Path(tempfile.gettempdir())
        out_path = tmp_dir / f"beverly_out_{update.effective_user.id}.jpg"

        try:
            out_bytes = gemini_tryon(
                user_photo_path=user_photo_path,
                asset_path=asset_path,
                logo_path=LOGO_PATH,
                tshirt=tshirt,
                color=color,
                pr=pr,
            )
            out_path.write_bytes(out_bytes)

            with open(out_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption=f"Готово ✅\n{tshirt} / {color} / {pr}",
                )
        except Exception as e:
            logger.exception("Generation failed")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ошибка генерации: {e}",
            )
        return

    await query.edit_message_text("Неизвестная команда кнопки. Нажми /start и попробуй снова.")


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set in environment variables")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in environment variables")

    catalog = load_catalog()
    logger.info("Catalog loaded: %d tshirts", len(catalog))
    logger.info("Gemini model: %s", GEMINI_IMAGE_MODEL)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.bot_data["catalog"] = catalog

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
