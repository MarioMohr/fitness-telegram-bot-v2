import os
import logging
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from database import (
    init_db,
    log_pool_status,
    save_weight_and_get_ewma,
    toggle_nutrient_log,
    get_recent_weight_logs,
    save_soreness_log,
    save_body_measures,
    get_latest_body_measures,
    get_local_now
)
from services.parser import (
    parse_weight_input,
    parse_soreness_input,
    parse_body_measures_input
)

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

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS_RAW or not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS

def is_night_lock() -> bool:
    current_hour = get_local_now().hour
    return current_hour >= 22 or current_hour < 7

def get_status_overview(is_hol: bool, is_rain: bool) -> str:
    hol_str = "🟢 ENABLED" if is_hol else "🔴 DISABLED"
    rain_str = "🟢 ENABLED" if is_rain else "🔴 DISABLED"
    hours_str = "🔴 DISABLED" if is_night_lock() else "🟢 ENABLED"

    return (
        "CURRENT STATES:\n"
        f"🌴 Holiday: {hol_str}\n"
        f"🌧️ Raining: {rain_str}\n"
        f"🏊 7 AM to 10 PM: {hours_str}"
    )

def build_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🏊 Pool Status"), KeyboardButton("☕ Nutrients")],
        [KeyboardButton("📊 Stats, Measures & Goals")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_pool_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Status: Empty")],
        [KeyboardButton("Status: Partially Occupied")],
        [KeyboardButton("Status: Full")],
        [KeyboardButton("🌴 Public Holiday"), KeyboardButton("🌧️ Raining")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_nutrients_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("☕ Mark: Cacao / Cashews Taken")],
        [KeyboardButton("❌ Mark: Not Taken Today")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_measures_inline_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("Chest -1", callback_data="adj_chest_-1"),
            InlineKeyboardButton("Chest +1", callback_data="adj_chest_1"),
        ],
        [
            InlineKeyboardButton("Arms -1", callback_data="adj_arms_-1"),
            InlineKeyboardButton("Arms +1", callback_data="adj_arms_1"),
        ],
        [
            InlineKeyboardButton("Waist -1", callback_data="adj_waist_-1"),
            InlineKeyboardButton("Waist +1", callback_data="adj_waist_1"),
        ],
        [
            InlineKeyboardButton("Hip -1", callback_data="adj_hip_-1"),
            InlineKeyboardButton("Hip +1", callback_data="adj_hip_1"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_stats_summary_text() -> str:
    df = get_recent_weight_logs(limit=5)
    chest, arms, waist, hip = get_latest_body_measures()

    chest_str = f"{chest} cm" if chest is not None else "N/A"
    arms_str = f"{arms} cm" if arms is not None else "N/A"
    waist_str = f"{waist} cm" if waist is not None else "N/A"
    hip_str = f"{hip} cm" if hip is not None else "N/A"

    weight_text = "No recent weight recorded."
    if not df.empty:
        weight_text = "\n".join([f"• {row['weight_kg']} kg ({row['timestamp'][:16]})" for _, row in df.iterrows()])

    return (
        "📊 Stats, Measures & Goals\n\n"
        "📐 Current Body Measurements:\n"
        f"• Chest: {chest_str}\n"
        f"• Arms: {arms_str}\n"
        f"• Waist: {waist_str}\n"
        f"• Hip: {hip_str}\n\n"
        f"⚖️ Recent Weight Entries:\n{weight_text}\n\n"
        "Adjust measurements using the quick buttons below or type inputs directly anytime (e.g. 134 chest, 49 arms)."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    welcome_text = (
        "Welcome to Fitness Trainer V3!\n\n"
        "Use the menu below to navigate or type direct inputs like:\n"
        "• 132 kg / 84.5 kg\n"
        "• My legs are sore\n"
        "• 134 chest / 49 arms / 131 hip / 110 waist / one three one hip"
    )
    await update.message.reply_text(welcome_text, reply_markup=build_main_menu())

async def measures_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("adj_"):
        return

    parts = data.split("_")
    part_name = parts[1]
    delta = float(parts[2])

    chest, arms, waist, hip = get_latest_body_measures()

    c = chest if part_name == "chest" else None
    a = arms if part_name == "arms" else None
    w = waist if part_name == "waist" else None
    h = hip if part_name == "hip" else None

    if part_name == "chest":
        c = (chest or 100.0) + delta
    elif part_name == "arms":
        a = (arms or 35.0) + delta
    elif part_name == "waist":
        w = (waist or 90.0) + delta
    elif part_name == "hip":
        h = (hip or 100.0) + delta

    save_body_measures(c, a, w, h)
    
    updated_text = generate_stats_summary_text()
    await query.edit_message_text(
        text=updated_text,
        reply_markup=build_measures_inline_keyboard()
    )

async def text_input_parser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    try:
        text = update.message.text.strip()
        text_lower = text.lower()

        if "back to main menu" in text_lower:
            await update.message.reply_text("Main Menu:", reply_markup=build_main_menu())
            return

        if text_lower == "🏊 pool status":
            is_hol = context.user_data.get('pool_holiday', False)
            is_rain = context.user_data.get('pool_rain', False)
            status_overview = get_status_overview(is_hol, is_rain)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Pool Status & Conditions\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        if "public holiday" in text_lower:
            current_state = context.user_data.get('pool_holiday', False)
            new_state = not current_state
            context.user_data['pool_holiday'] = new_state
            is_rain = context.user_data.get('pool_rain', False)
            status_overview = get_status_overview(new_state, is_rain)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Holiday Status Toggled\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        if "raining" in text_lower:
            current_state = context.user_data.get('pool_rain', False)
            new_state = not current_state
            context.user_data['pool_rain'] = new_state
            is_hol = context.user_data.get('pool_holiday', False)
            status_overview = get_status_overview(is_hol, new_state)
            last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
            msg = f"🏊 Rain Status Toggled\n\n{status_overview}\n\n{last_logged}"
            await update.message.reply_text(msg, reply_markup=build_pool_menu())
            return

        if any(term in text_lower for term in ["status: empty", "status: partially occupied", "status: full", "empty", "full"]):
            if is_night_lock():
                await update.message.reply_text(
                    "⛔ Pool is currently closed (10 PM to 7 AM). Cannot log occupancy right now.",
                    reply_markup=build_main_menu()
                )
                return

            is_hol = context.user_data.get('pool_holiday', False)
            is_rain = context.user_data.get('pool_rain', False)
            
            if "empty" in text_lower:
                occ_label = "empty"
            elif "partially" in text_lower:
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

        if "stats, measures & goals" in text_lower:
            summary_text = generate_stats_summary_text()
            await update.message.reply_text(
                summary_text,
                reply_markup=build_measures_inline_keyboard()
            )
            return

        parsed_measures = parse_body_measures_input(text)
        if parsed_measures:
            c = parsed_measures.get('chest')
            a = parsed_measures.get('arms')
            w = parsed_measures.get('waist')
            h = parsed_measures.get('hip')
            
            new_c, new_a, new_w, new_h = save_body_measures(c, a, w, h)
            
            reply = (
                "📐 Body Measurements Recorded!\n\n"
                f"• Chest: {new_c if new_c is not None else 'N/A'} cm\n"
                f"• Arms: {new_a if new_a is not None else 'N/A'} cm\n"
                f"• Waist: {new_w if new_w is not None else 'N/A'} cm\n"
                f"• Hip: {new_h if new_h is not None else 'N/A'} cm"
            )
            await update.message.reply_text(reply, reply_markup=build_main_menu())
            return

        parsed_weight = parse_weight_input(text)
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
    app.add_handler(CallbackQueryHandler(measures_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_parser))

    logger.info("Starting Fitness Container V3...")
    app.run_polling()

if __name__ == "__main__":
    main()

