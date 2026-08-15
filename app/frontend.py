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

from backend import (
    init_db,
    log_pool_status,
    save_weight_and_get_ewma,
    toggle_nutrient_log,
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
from services.measures_body import generate_body_measurements_image
from services.stats_wma import generate_weight_chart

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
        [KeyboardButton("📐 Measures"), KeyboardButton("⚖️ Weight Stats")]
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

def build_measures_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Chest -1"), KeyboardButton("Chest +1")],
        [KeyboardButton("Arms -1"), KeyboardButton("Arms +1")],
        [KeyboardButton("Waist -1"), KeyboardButton("Waist +1")],
        [KeyboardButton("Hip -1"), KeyboardButton("Hip +1")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def send_body_image_or_fallback():
    chest, arms, waist, hip = get_latest_body_measures()

    chest_val = str(int(round(chest))) if chest is not None else "--"
    arms_val = str(int(round(arms))) if arms is not None else "--"
    waist_val = str(int(round(waist))) if waist is not None else "--"
    hip_val = str(int(round(hip))) if hip is not None else "--"

    return generate_body_measurements_image(
        chest=chest_val,
        arms=arms_val,
        waist=waist_val,
        hip=hip_val
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

        if text_lower == "📐 measures":
            image_path = send_body_image_or_fallback()
            caption_text = "📐 BODY MEASURES\n\nAdjust measurements using the menu below or type inputs directly anytime."
            
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=caption_text,
                        reply_markup=build_measures_menu()
                    )
            else:
                await update.message.reply_text(
                    caption_text,
                    reply_markup=build_measures_menu()
                )
            return

        if text_lower == "⚖️ weight stats":
            chart_path = generate_weight_chart()
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption="⚖️ WEIGHT HISTORY & TREND (EWMA)",
                        reply_markup=build_main_menu()
                    )
            else:
                await update.message.reply_text(
                    "⚖️ No weight history recorded yet. Enter your weight to generate the chart!",
                    reply_markup=build_main_menu()
                )
            return

        measure_adjustments = {
            "chest -1": ("chest", -1.0),
            "chest +1": ("chest", 1.0),
            "arms -1": ("arms", -1.0),
            "arms +1": ("arms", 1.0),
            "waist -1": ("waist", -1.0),
            "waist +1": ("waist", 1.0),
            "hip -1": ("hip", -1.0),
            "hip +1": ("hip", 1.0),
        }

        if text_lower in measure_adjustments:
            part_name, delta = measure_adjustments[text_lower]
            chest, arms, waist, hip = get_latest_body_measures()

            c = (chest or 134.0) + delta if part_name == "chest" else chest
            a = (arms or 49.0) + delta if part_name == "arms" else arms
            w = (waist or 110.0) + delta if part_name == "waist" else waist
            h = (hip or 131.0) + delta if part_name == "hip" else hip

            save_body_measures(c, a, w, h)

            image_path = send_body_image_or_fallback()
            caption_text = "📐 BODY MEASURES\n\nAdjust measurements using the menu below or type inputs directly anytime."

            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=caption_text,
                        reply_markup=build_measures_menu()
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
                f"• Chest: {int(round(new_c)) if new_c is not None else 'N/A'} cm\n"
                f"• Arms: {int(round(new_a)) if new_a is not None else 'N/A'} cm\n"
                f"• Waist: {int(round(new_w)) if new_w is not None else 'N/A'} cm\n"
                f"• Hip: {int(round(new_h)) if new_h is not None else 'N/A'} cm"
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_parser))

    logger.info("Starting Fitness Container V3...")
    app.run_polling()

if __name__ == "__main__":
    main()

