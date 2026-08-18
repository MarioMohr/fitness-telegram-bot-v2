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
    log_pool_status,
    save_weight_and_get_ewma,
    toggle_nutrient_log,
    save_soreness_log,
    get_local_now
)
from services.parser import (
    parse_weight_input,
    parse_soreness_input
)
from services.sizes import handle_sizes_command
from services.stats_wma import generate_weight_chart
from services.stats_goals import goals_service

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

def build_weight_menu(height_cm: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🧮 Ideal Weight Calculator")],
        [KeyboardButton(f"📏 Set Height ({height_cm} cm)")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_frame_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Slim")],
        [KeyboardButton("Normal")],
        [KeyboardButton("Heavy / Broad")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_look_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Athletic")],
        [KeyboardButton("Fit / Normal")],
        [KeyboardButton("Soft / Fluffy")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_confirm_target_menu(calculated_weight: float) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(f"✅ Accept {calculated_weight} kg")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    welcome_text = (
        "Welcome to Fitness Trainer V2.1!\n\n"
        "Use the menu below to navigate.\n\n"
        "Update your weight by type direct inputs like:\n"
        "• 92 kg\n"
        "• 84.5 kg\n"
        "• 11,500 gram\n\n"
        "To avoid working out specific body parts type:\n"
        "[Cramps | Pain | Acidity | Soreness]\n"
        "And comine it with a body part like:\n"
        "[Arms | Chest | Chest | Legs | Stomach | Glutes]"
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
            context.user_data.pop('awaiting_height', None)
            context.user_data.pop('calc_step', None)
            context.user_data.pop('pending_calculated_weight', None)
            await update.message.reply_text("Main Menu:", reply_markup=build_main_menu())
            return

        if await handle_sizes_command(update, context):
            return

        if context.user_data.get('awaiting_height'):
            height_match = re.search(r'\b(1[4-9][0-9]|2[0-2][0-9])\b', text_lower)
            if height_match:
                new_height = int(height_match.group(1))
                context.user_data['user_height'] = new_height
                context.user_data['awaiting_height'] = False
                await update.message.reply_text(
                    f"📏 Height updated to **{new_height} cm**!",
                    parse_mode="Markdown",
                    reply_markup=build_weight_menu(new_height)
                )
                return
            else:
                await update.message.reply_text(
                    "Please enter a valid height in cm (e.g. 175).",
                    reply_markup=build_weight_menu(context.user_data.get('user_height', 175))
                )
                return

        if text_lower == "🧮 ideal weight calculator":
            context.user_data['calc_step'] = 'frame'
            await update.message.reply_text(
                "🧮 **Step 1:** Select your body frame type:",
                parse_mode="Markdown",
                reply_markup=build_frame_menu()
            )
            return

        if context.user_data.get('calc_step') == 'frame' and text_lower in ["slim", "normal", "heavy / broad", "heavy"]:
            frame_val = "heavy" if "heavy" in text_lower else text_lower
            context.user_data['calc_frame'] = frame_val
            context.user_data['calc_step'] = 'look'
            await update.message.reply_text(
                "🧮 **Step 2:** Select your desired target look:",
                parse_mode="Markdown",
                reply_markup=build_look_menu()
            )
            return

        if context.user_data.get('calc_step') == 'look' and text_lower in ["athletic", "fit / normal", "soft / fluffy", "fit", "fluffy"]:
            look_val = "fit" if "fit" in text_lower else ("fluffy" if "fluffy" in text_lower else text_lower)
            frame_val = context.user_data.get('calc_frame', 'normal')
            height_val = context.user_data.get('user_height', 175)

            target_weight = goals_service.calculate_ideal_weight(height_val, frame_val, look_val)
            context.user_data['pending_calculated_weight'] = target_weight
            context.user_data['calc_step'] = 'confirm_target'

            result_text = goals_service.format_calculation_result(height_val, frame_val, look_val, target_weight)
            await update.message.reply_text(
                result_text,
                parse_mode="Markdown",
                reply_markup=build_confirm_target_menu(target_weight)
            )
            return

        if context.user_data.get('calc_step') == 'confirm_target':
            pending_val = context.user_data.get('pending_calculated_weight')
            target_w = None

            if "accept" in text_lower or text_lower in ["yes", "ja", "ok"]:
                target_w = pending_val
            else:
                weight_num_match = re.search(r'\b([3-9][0-9]|1[0-9][0-9])(?:[\.,][0-9])?\b', text_lower)
                if weight_num_match:
                    target_w = float(weight_num_match.group(0).replace(',', '.'))

            if target_w is not None:
                context.user_data['target_weight'] = target_w
                context.user_data['calc_step'] = None
                context.user_data.pop('pending_calculated_weight', None)

                chart_path = generate_weight_chart(target_weight=target_w)
                caption_msg = f"🎯 Target weight set to **{target_w} kg**!"

                if chart_path and os.path.exists(chart_path):
                    with open(chart_path, 'rb') as photo:
                        await update.message.reply_photo(
                            photo=photo,
                            caption=caption_msg,
                            parse_mode="Markdown",
                            reply_markup=build_main_menu()
                        )
                else:
                    await update.message.reply_text(
                        caption_msg,
                        parse_mode="Markdown",
                        reply_markup=build_main_menu()
                    )
                return

        if "set height" in text_lower:
            context.user_data['awaiting_height'] = True
            await update.message.reply_text(
                "📏 Please type your height in centimeters (e.g. 175):",
                reply_markup=build_weight_menu(context.user_data.get('user_height', 175))
            )
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

        if text_lower == "⚖️ weight stats":
            target_w = context.user_data.get('target_weight', None)
            current_h = context.user_data.get('user_height', 175)
            chart_path = generate_weight_chart(target_weight=target_w)
            
            keyboard = build_weight_menu(current_h)
            
            caption_msg = "⚖️ WEIGHT HISTORY & TREND (EWMA)"
            if target_w:
                caption_msg += f"\n🎯 Current Target: {target_w} kg"

            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=caption_msg,
                        reply_markup=keyboard
                    )
            else:
                await update.message.reply_text(
                    "⚖️ No weight history recorded yet. Enter your weight to generate the chart!",
                    reply_markup=keyboard
                )
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

    logger.info("Starting Fitness Container V2...")
    app.run_polling()

if __name__ == "__main__":
    main()

