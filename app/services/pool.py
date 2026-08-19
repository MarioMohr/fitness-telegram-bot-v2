from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from backend import (
    log_pool_status,
    get_pool_best_times,
    get_local_now
)

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

def build_pool_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton("Status: Empty"),
            KeyboardButton("Status: Partially"),
            KeyboardButton("Status: Full")
        ],
        [
            KeyboardButton("🌴 Public Holiday"),
            KeyboardButton("🌧️ Raining")
        ],
        [
            KeyboardButton("🏊 Best Times"),
            KeyboardButton("⬅️ Back to Main Menu")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def handle_pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE, build_main_menu) -> bool:
    text = update.message.text.strip()
    text_lower = text.lower()

    if text_lower == "🏊 pool status":
        is_hol = context.user_data.get('pool_holiday', False)
        is_rain = context.user_data.get('pool_rain', False)
        status_overview = get_status_overview(is_hol, is_rain)
        last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
        msg = f"🏊 Pool Status & Conditions\n\n{status_overview}\n\n{last_logged}"
        await update.message.reply_text(msg, reply_markup=build_pool_menu())
        return True

    if "public holiday" in text_lower:
        current_state = context.user_data.get('pool_holiday', False)
        new_state = not current_state
        context.user_data['pool_holiday'] = new_state
        is_rain = context.user_data.get('pool_rain', False)
        status_overview = get_status_overview(new_state, is_rain)
        last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
        msg = f"🏊 Holiday Status Toggled\n\n{status_overview}\n\n{last_logged}"
        await update.message.reply_text(msg, reply_markup=build_pool_menu())
        return True

    if "raining" in text_lower:
        current_state = context.user_data.get('pool_rain', False)
        new_state = not current_state
        context.user_data['pool_rain'] = new_state
        is_hol = context.user_data.get('pool_holiday', False)
        status_overview = get_status_overview(is_hol, new_state)
        last_logged = context.user_data.get('last_pool_log', "No data recorded yet.")
        msg = f"🏊 Rain Status Toggled\n\n{status_overview}\n\n{last_logged}"
        await update.message.reply_text(msg, reply_markup=build_pool_menu())
        return True

    if text_lower == "🏊 best times":
        best_times_summary = get_pool_best_times()
        msg = f"🏊 **Pool Best Times Breakdown**\n\n{best_times_summary}"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_pool_menu())
        return True

    if any(term in text_lower for term in ["status: empty", "status: partially", "status: full", "empty", "partially", "full"]):
        if is_night_lock():
            await update.message.reply_text(
                "⛔ Pool is currently closed (10 PM to 7 AM). Cannot log occupancy right now.",
                reply_markup=build_main_menu()
            )
            return True

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
        return True

    return False

