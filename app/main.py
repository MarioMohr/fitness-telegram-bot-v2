import os
import re
import sqlite3
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
DB_PATH = "/app/data/fitness.db"

# Read timezone from environment variable
TZ_NAME = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")

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

def get_local_now() -> datetime:
    """Returns current datetime in configured timezone."""
    try:
        return datetime.now(ZoneInfo(TZ_NAME))
    except Exception as e:
        logger.error(f"Error loading timezone {TZ_NAME}: {e}")
        return datetime.now()

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

# --- Database Setup ---

def init_db() -> None:
    """Initializes SQLite database schemas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR REPLACE INTO system_info (key, value) VALUES ('version', '3.0')")
    cursor.execute("INSERT OR REPLACE INTO system_info (key, value) VALUES ('project_name', 'Fitness Container V3')")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            occupancy TEXT NOT NULL,
            is_holiday INTEGER DEFAULT 0,
            is_raining INTEGER DEFAULT 0,
            recommendation TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            weight_kg REAL NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS body_measures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            chest_cm REAL,
            arms_cm REAL,
            waist_cm REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nutrient_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            cacao_cashews_taken INTEGER NOT NULL DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("Database schemas verified.")

def log_pool_status(occupancy: str, is_holiday: bool, is_raining: bool) -> None:
    """Saves pool log to DB."""
    now_iso = get_local_now().isoformat()
    hol_int = 1 if is_holiday else 0
    rain_int = 1 if is_raining else 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pool_logs (timestamp, occupancy, is_holiday, is_raining, recommendation) VALUES (?, ?, ?, ?, ?)",
        (now_iso, occupancy, hol_int, rain_int, "")
    )
    conn.commit()
    conn.close()

def save_weight_and_get_ewma(weight_kg: float) -> tuple[float, float]:
    """Saves weight and calculates 7-day EWMA trend."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO weight_logs (weight_kg) VALUES (?)", (weight_kg,))
    conn.commit()

    df = pd.read_sql_query("SELECT timestamp, weight_kg FROM weight_logs", conn)
    conn.close()

    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    daily_df = df.groupby('date')['weight_kg'].mean().reset_index()
    daily_df = daily_df.sort_values('date')

    daily_df['ewma_7d'] = daily_df['weight_kg'].ewm(span=7, adjust=False).mean()

    latest_daily_avg = daily_df.iloc[-1]['weight_kg']
    latest_ewma = daily_df.iloc[-1]['ewma_7d']

    return float(latest_daily_avg), float(latest_ewma)

def toggle_nutrient_log(status: int) -> str:
    """Toggles daily nutrient intake record."""
    today_str = get_local_now().date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO nutrient_logs (date, cacao_cashews_taken) VALUES (?, ?)", (today_str, status))
    conn.commit()
    conn.close()
    return "Taken" if status == 1 else "Not Taken"

def clean_number(num_str: str) -> float:
    """Cleans up numeric inputs for float conversion."""
    num_str = num_str.strip()
    if '.' in num_str and ',' in num_str:
        num_str = num_str.replace('.', '').replace(',', '.')
    elif '.' in num_str:
        parts = num_str.split('.')
        if len(parts[-1]) == 3 and len(parts) > 1:
            num_str = num_str.replace('.', '')
    elif ',' in num_str:
        parts = num_str.split(',')
        if len(parts[-1]) == 3 and len(parts) > 1:
            num_str = num_str.replace(',', '')
        else:
            num_str = num_str.replace(',', '.')
    return float(num_str)

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

        # Pool Status Logging (Only allowed during opening hours 7 AM to 10 PM)
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
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT weight_kg, timestamp FROM weight_logs ORDER BY id DESC LIMIT 5", conn)
            conn.close()
            
            history_text = ""
            if not df.empty:
                history_text = "\n\nRecent Entries:\n" + "\n".join([f"• {row['weight_kg']} kg ({row['timestamp'][:16]})" for _, row in df.iterrows()])
                
            await update.message.reply_text(
                f"📊 Stats, Measures & Goals{history_text}\n\nType your weight anytime (e.g., '84.5 kg').",
                reply_markup=build_main_menu()
            )
            return

        # Direct Weight Input (kg or g)
        kg_pattern = r'([\d\.,\s]+)\s*(kg|kilos|kilo|kilogram|kilograms|weighed)'
        kg_match = re.search(kg_pattern, text_lower)
        if kg_match:
            try:
                val = clean_number(kg_match.group(1))
                daily_avg, ewma = save_weight_and_get_ewma(val)
                reply = (
                    f"⚖️ Weight Logged Successfully!\n\n"
                    f"• Measured Value: {val:.1f} kg\n"
                    f"• Today's Average: {daily_avg:.1f} kg\n"
                    f"• 7-Day EWMA Trend: {ewma:.2f} kg"
                )
                await update.message.reply_text(reply, reply_markup=build_main_menu())
                return
            except ValueError:
                pass

        gram_pattern = r'([\d\.,\s]+)\s*(g|gram|gramm|grams)'
        gram_match = re.search(gram_pattern, text_lower)
        if gram_match:
            try:
                raw_grams = clean_number(gram_match.group(1))
                val_kg = raw_grams / 1000.0
                daily_avg, ewma = save_weight_and_get_ewma(val_kg)
                reply = (
                    f"⚖️ Weight Logged Successfully! ({raw_grams:.0f} g converted)\n\n"
                    f"• Measured Value: {val_kg:.1f} kg\n"
                    f"• Today's Average: {daily_avg:.1f} kg\n"
                    f"• 7-Day EWMA Trend: {ewma:.2f} kg"
                )
                await update.message.reply_text(reply, reply_markup=build_main_menu())
                return
            except ValueError:
                pass

        # Comprehensive Soreness & Pain Detection (EN & DE Slang included)
        body_parts_map = {
            'leg': 'legs', 'legs': 'legs', 'beine': 'legs', 'bein': 'legs',
            'knee': 'knees', 'knees': 'knees', 'knie': 'knees',
            'arm': 'arms', 'arms': 'arms', 'arme': 'arms', 'arm': 'arms',
            'shoulder': 'shoulders', 'shoulders': 'shoulders', 'schulter': 'shoulders', 'schultern': 'shoulders',
            'chest': 'chest', 'breast': 'chest', 'brust': 'chest', 'tits': 'chest', 'titties': 'chest', 'busen': 'chest', 'boobs': 'chest', 'man boobs': 'chest', 'männerbrust': 'chest',
            'neck': 'neck', 'nacken': 'neck',
            'stomach': 'abs/stomach', 'abs': 'abs/stomach', 'core': 'abs/stomach', 'bauch': 'abs/stomach',
            'back': 'back', 'rücken': 'back',
            'calf': 'calves', 'calves': 'calves', 'wade': 'calves', 'waden': 'calves',
            'glute': 'glutes', 'glutes': 'glutes', 'butt': 'glutes', 'po': 'glutes', 'arsch': 'glutes', 'hintern': 'glutes'
        }
        
        soreness_triggers = ['sore', 'hurt', 'hurts', 'pain', 'aching', 'stiff', 'weh', 'wehe', 'schmerz', 'schmerzen', 'muskelkater', 'steif']
        
        if any(trigger in text_lower for trigger in soreness_triggers):
            detected_parts = []
            for word, canonical_part in body_parts_map.items():
                if word in text_lower and canonical_part not in detected_parts:
                    detected_parts.append(canonical_part)
            
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

