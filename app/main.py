import os
import logging
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from database import (
    init_db,
    log_pool_status,
    save_weight_and_get_ewma,
    toggle_nutrient_log,
    get_recent_weight_logs,
    get_local_now
)
from services.parser import (
    parse_weight_input,
    parse_soreness_input
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# Read allowed Telegram User IDs
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [
    int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()
]

# --- Helper Functions ---

def is_authorized(user_id: int) -> bool:
    """Checks if the user ID is permitted to use the bot."""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS

def is_night_lock() -> bool:
    """Returns True if local time is between 22:00 and 07:00."""
    current_hour = get_local_now().hour
    return current_hour >= 22 or current_hour < 7

def get_status_overview(is_hol: bool, is_rain: bool) -> str:
    """Generates aligned CURRENT STATES overview."""
    hol_str = "🟢 ENABLED" if is_hol else "🔴 DISABLED"
    rain_str = "🟢 ENABLED" if is_rain else "🔴 DISABLED"
    
    if is_night_lock():
        hours_str = "🔴 DISABLED"
    else:
        hours_str = "🟢 ENABLED"

    return (
        "CURRENT STATES:\n"
        f"🌴 Holiday: {hol_str}\n"
        f"🌧️ Raining: {rain_str}\n"
        f"🏊 7 AM to 10 PM: {hours_str}"
    )

# --- Keyboards & Menus ---

def build_main_menu() -> ReplyKeyboardMarkup:
    """Builds main navigation menu."""
    keyboard = [
        [KeyboardButton("🏊 Pool Status"), KeyboardButton("☕ Nutrients")],
        [KeyboardButton("📊 Stats, Measures & Goals")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_pool_menu() -> ReplyKeyboardMarkup:
    """Builds pool status sub-menu."""
    keyboard = [
        [KeyboardButton("Status: Empty")],
        [KeyboardButton("Status: Partially Occupied")],
        [KeyboardButton("Status: Full")],
        [KeyboardButton("🌴 Public Holiday"), KeyboardButton("🌧️ Raining")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_nutrients_menu() -> ReplyKeyboardMarkup:
    """Builds nutrients sub-menu."""
    keyboard = [
        [KeyboardButton("☕ Mark: Cacao / Cashews Taken")],
        [KeyboardButton("❌ Mark: Not Taken Today")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Telegram Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by ID: {user_id}")
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    welcome_text = (
        "Welcome to Fitness Trainer V3!\n\n"
        "Use the menu below to navigate or type direct inputs like:\n"
        "• 132 kg / 84.5 kg / 132000 g\n"
        "• My legs are sore / Meine Knie tun weh / My boobs hurt"
    )
    await update.message.reply_text(welcome_text, reply_markup=build_main_menu())

async def text_input_parser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized text input from ID: {user_id}")
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    try:
        text = update.message.text.strip()
        text_lower = text.lower()

        # Navigation
        if "back to main menu" in text_lower or "zurück zum hauptmenü" in text_lower:
            await update.message.reply_text("Main Menu:", reply_markup=build_main_menu())
            return

        # Open Pool Menu
        if text_lower == "🏊 pool status":
            is_hol = context.user_data.get('pool_holiday', False)
            is_rain = context.user_data.get('pool_rain', False)
            status_overview = get_status_overview(is_hol, is_rain)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Pool Status & Conditions\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        # Holiday Toggle
        if "public holiday" in text_lower or "feiertag" in text_lower:
            current_state = context.user_data.get('pool_holiday', False)
            new_state = not current_state
            context.user_data['pool_holiday'] = new_state
            is_rain = context.user_data.get('pool_rain', False)
            status_overview = get_status_overview(new_state, is_rain)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Holiday Status Toggled\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        # Rain Toggle
        if "raining" in text_lower or "regen" in text_lower:
            current_state = context.user_data.get('pool_rain', False)
            new_state = not current_state
            context.user_data['pool_rain'] = new_state
            is_hol = context.user_data.get('pool_holiday', False)
            status_overview = get_status_overview(is_hol, new_state)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Rain Status Toggled\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        # Pool Status Logging
        if any(term in text_lower for term in ["status: empty", "status: leer", "status: partially occupied", "status: teilweise belegt", "status: full", "status: voll", "empty", "full"]):
            if is_night_lock():
                await update.message.reply_text(
                    "⛔ Pool is currently closed (10 PM to 7 AM). Cannot log occupancy right now.",
                    reply_markup=build_main_menu()
                )
                return

            is_hol = context.user_data.get('pool_holiday', False)
            is_rain = context.user_data.get('pool_rain', False)
            
            if "empty" in text_lower or "leer" in text_lower:
                occ_label = "empty"
            elif "partially" in text_lower or "teilweise" in text_lower:
                occ_label = "partially occupied"
            else:
                occ_label = "full"

            log_pool_status(occ_label.capitalize(), is_hol, is_rain)
            
            log_str = f"Pool logged as {occ_label}."
            context.user_data['last_pool_log'] = log_str
            
            status_overview = get_status_overview(is_hol, is_rain)
            msg = f"🏊 Pool Status & Conditions\n\n{status_overview}\n\n{log_str}"
            await update.message.reply_text(msg, reply_markup=build_main_menu())
            return

        # Nutrients Menu
        if text_lower == "☕ nutrients":
            await update.message.reply_text(
                "☕ Nutrients Tracker\n\nRecord intake for healthy fats & magnesium synthesis:",
                reply_markup=build_nutrients_menu()
            )
            return

        if "cacao" in text_lower or "cashews taken" in text_lower or "cargill kakaomasse" in text_lower:
            res = toggle_nutrient_log(1)
            await update.message.reply_text(f"☕ Cargill Cacao / Cashews: {res}", reply_markup=build_main_menu())
            return

        if "not taken today" in text_lower or "heute nicht eingenommen" in text_lower:
            res = toggle_nutrient_log(0)
            await update.message.reply_text(f"❌ Cargill Cacao / Cashews: {res}", reply_markup=build_main_menu())
            return

        # Stats & Weight Logs
        if "stats, measures & goals" in text_lower:
            df = get_recent_weight_logs(limit=5)
            
            history_text = ""
            if not df.empty:
                history_text = "\n\nRecent Entries:\n" + "\n".join([f"• {row['weight_kg']} kg ({row['timestamp'][:16]})" for _, row in df.iterrows()])
                
            await update.message.reply_text(
                f"📊 Stats, Measures & Goals{history_text}\n\nType your weight anytime (e.g., '84.5 kg').",
                reply_markup=build_main_menu()
            )
            return

        # Direct Weight Input
        parsed_weight = parse_weight_input(text_lower)
        if parsed_weight is not None:
            daily_avg, ewma = save_weight_and_get_ewma(parsed_weight)
            reply = (
                f"⚖️ Weight Logged Successfully!\n\n"
                f"• Measured Value: {parsed_weight:.1f} kg\n"
                f"• Today's Average: {daily_avg:.1f} kg\n"
                f"• 7-Day EWMA Trend: {ewma:.2f} kg"
            )
            await update.message.reply_text(reply, reply_markup=build_main_menu())
            return

        # Direct Soreness Input
        detected_parts = parse_soreness_input(text_lower)
        if detected_parts is not None:
            part_str = ", ".join([p.upper() for p in detected_parts]) if detected_parts else "BODY PART"
            await update.message.reply_text(
                f"🩹 Soreness / Pain Recorded for: {part_str}.",
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

    logger.info("Starting Fitness Container V3...")
    app.run_polling()

if __name__ == "__main__":
    main()

