import os
import re
import logging
from dotenv import load_dotenv
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from backend import (
    init_db,
    save_weight_and_get_ewma,
    toggle_nutrient_log,
    save_soreness_log
)
from services.parser import (
    parse_weight_input,
    parse_soreness_input
)
from services.sizes import handle_sizes_command
from services.weight import handle_weight_command, calculate_progress_summary
from services.pool import handle_pool_command

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

ALLOWED_USERS_RAW = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [
    int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()
]

APP_VERSION = os.getenv("APP_VERSION", "2.5")

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS_RAW or not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS

def build_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🏊 Pool Status"), KeyboardButton("☕ Nutrients")],
        [KeyboardButton("📐 Measures"), KeyboardButton("⚖️ Weight")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_nutrients_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("☕ Mark: Cacao / Cashews Taken")],
        [KeyboardButton("❌ Mark: Not Taken Today")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    welcome_text = (
        f"Welcome to the Metabolic Sniper V{APP_VERSION}!\n\n"
        "To avoid working out specific body parts type:\n"
        "• Cramps\n"
        "• Pain\n"
        "• Soreness\n"
        "And combine it with a body part like:\n"
        "• Arms\n"
        "• Chest\n"
        "• Legs\n"
        "• Stomach\n"
        "• Glutes\n\n"
        "Use the menu on the bottom to navigate."
    )
    await update.message.reply_text(welcome_text, reply_markup=build_main_menu())

async def text_input_parser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    try:
        text = update.message.text.strip()
        text_lower = text.lower()

        if "back to main menu" in text_lower or "⬅️ back to main menu" in text_lower:
            context.user_data.pop('calc_step', None)
            context.user_data.pop('pending_calculated_weight', None)
            await update.message.reply_text("Main Menu:", reply_markup=build_main_menu())
            return

        if await handle_sizes_command(update, context):
            return

        if await handle_weight_command(update, context, build_main_menu):
            return

        if await handle_pool_command(update, context, build_main_menu):
            return

        if text_lower == "☕ nutrients":
            await update.message.reply_text(
                "☕ Nutrients Tracker\n\nRecord intake for healthy fats & magnesium synthesis:",
                reply_markup=build_nutrients_menu()
            )
            return

        if "cacao" in text_lower or "cashews taken" in text_lower:
            res = toggle_nutrient_log(1)
            await update.message.reply_text(f"☕ Cargill Cacao / Cashews: {res}", reply_markup=build_main_menu())
            return

        if "not taken today" in text_lower:
            res = toggle_nutrient_log(0)
            await update.message.reply_text(f"❌ Cargill Cacao / Cashews: {res}", reply_markup=build_main_menu())
            return

        parsed_weight = parse_weight_input(text)
        if parsed_weight is not None:
            daily_avg, ewma = save_weight_and_get_ewma(parsed_weight)
            progress_summary = calculate_progress_summary()
            
            reply = (
                f"⚖️ **Weight Logged Successfully!**\n\n"
                f"• **Measured Value:** {parsed_weight:.1f} kg\n"
                f"• **Today's Average:** {daily_avg:.1f} kg\n"
                f"• **7-Day EWMA Trend:** {ewma:.2f} kg\n\n"
                f"{progress_summary}"
            )
            await update.message.reply_text(reply, parse_mode="Markdown", reply_markup=build_main_menu())
            return

        detected_parts = parse_soreness_input(text)
        if detected_parts is not None:
            save_soreness_log(detected_parts)
            part_str = ", ".join([p.upper() for p in detected_parts]) if detected_parts else "BODY PART"
            await update.message.reply_text(
                f"🩹 Soreness / Pain Recorded in Database for: {part_str}.",
                reply_markup=build_main_menu()
            )
            return

        await update.message.reply_text("Command not recognized.", reply_markup=build_main_menu())
    except Exception as err:
        logger.error(f"Error in text_input_parser: {err}")
        await update.message.reply_text(f"⚠️ Error processing command: {err}", reply_markup=build_main_menu())

def main() -> None:
    init_db()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token or not token.strip():
        logger.error("TELEGRAM_BOT_TOKEN is missing!")
        return

    app = Application.builder().token(token.strip()).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_parser))

    logger.info(f"Starting Fitness Container V{APP_VERSION}...")
    app.run_polling()

if __name__ == "__main__":
    main()

