import os
import re
import sqlite3
import logging
from datetime import datetime, date
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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

WORD_TO_NUM = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20,
    'thirty': 30, 'forty': 40, 'fifty': 50
}

# --- Database Setup & EWMA Calculation ---

def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # System info
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR REPLACE INTO system_info (key, value) VALUES ('version', '2.0')")
    cursor.execute("INSERT OR REPLACE INTO system_info (key, value) VALUES ('project_name', 'Fitness Trainer V2')")

    # Pool logs schema
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

    # Weight logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            weight_kg REAL NOT NULL
        )
    ''')

    # Body measurements
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS body_measures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            chest_cm REAL,
            arms_cm REAL,
            waist_cm REAL
        )
    ''')

    # Micro-Nutrient logs
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

def get_pool_occupancy_stats() -> str:
    """Calculates best times to swim per day of week based on historical data."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT timestamp, occupancy FROM pool_logs", conn)
    conn.close()

    if df.empty:
        return "📊 _No historical pool data available yet._"

    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
    df = df.dropna(subset=['datetime'])

    total_logs = len(df)
    empty_logs = df[df['occupancy'] == 'Empty'].copy()

    if empty_logs.empty:
        return f"📊 **Pool Analytics** ({total_logs} logs)\n_No 'Empty' states recorded so far._"

    empty_logs['day_num'] = empty_logs['datetime'].dt.dayofweek
    empty_logs['hour'] = empty_logs['datetime'].dt.hour

    days_map = {
        0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
        4: "Fri", 5: "Sat", 6: "Sun"
    }

    daily_lines = []
    for day_num in range(7):
        day_name = days_map[day_num]
        day_data = empty_logs[empty_logs['day_num'] == day_num]
        
        if day_data.empty:
            daily_lines.append(f"• **{day_name}:** `No data`")
        else:
            best_hour = day_data['hour'].value_counts().index[0]
            count = day_data['hour'].value_counts().iloc[0]
            time_slot = f"{best_hour:02d}:00 - {best_hour+1:02d}:00"
            daily_lines.append(f"• **{day_name}:** `{time_slot}` ({count}x empty)")

    stats_msg = (
        f"📊 **Weekly Best Swim Windows** ({total_logs} logs)\n"
        f"_Most frequent empty slots per day:_\n\n" +
        "\n".join(daily_lines)
    )
    return stats_msg

def save_weight_and_get_ewma(weight_kg: float) -> tuple[float, float]:
    """Saves raw weight to SQLite, computes daily averages, and returns (daily_avg, ewma_7d)."""
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
    today_str = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO nutrient_logs (date, cacao_cashews_taken) VALUES (?, ?)", (today_str, status))
    conn.commit()
    conn.close()
    return "Taken ✅" if status == 1 else "Not Taken ❌"

def clean_number(num_str: str) -> float:
    """Handles thousand separators and decimal points cleanly."""
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

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏊 Pool Status", callback_data="menu_pool")],
        [InlineKeyboardButton("🏋️ Sport & Training", callback_data="menu_sport")],
        [InlineKeyboardButton("📊 Stats, Measures & Goals", callback_data="menu_stats")],
        [InlineKeyboardButton("☕ Nutrients", callback_data="menu_nutrients")],
        [InlineKeyboardButton("🤖 Ollama AI Coach", callback_data="menu_coach")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_pool_menu(is_holiday: bool = False, is_raining: bool = False) -> InlineKeyboardMarkup:
    hol_label = "✅ Public Holiday" if is_holiday else "☐ Public Holiday"
    rain_label = "✅ Raining" if is_raining else "☐ Raining"

    keyboard = [
        [InlineKeyboardButton("Status: Empty", callback_data="pool_status_empty")],
        [InlineKeyboardButton("Status: Partially Occupied", callback_data="pool_status_partial")],
        [InlineKeyboardButton("Status: Full", callback_data="pool_status_full")],
        [InlineKeyboardButton(hol_label, callback_data="pool_toggle_holiday")],
        [InlineKeyboardButton(rain_label, callback_data="pool_toggle_rain")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_sport_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏊 Swim Log", callback_data="sport_swim"), InlineKeyboardButton("🥾 Walk / Trekking", callback_data="sport_walk")],
        [InlineKeyboardButton("🛕 Batu Caves", callback_data="sport_batu"), InlineKeyboardButton("🧘 DDP Yoga", callback_data="sport_ddpy")],
        [InlineKeyboardButton("🫁 Breathing / Apnea", callback_data="sport_breath"), InlineKeyboardButton("🏋️ Anatoly Workout", callback_data="sport_anatoly")],
        [InlineKeyboardButton("💥 High Intensity / Sex", callback_data="sport_sex")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_nutrients_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("☕ Mark: Cacao / Cashews Taken", callback_data="nutrient_yes")],
        [InlineKeyboardButton("❌ Mark: Not Taken Today", callback_data="nutrient_no")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = (
        "Welcome to **Fitness Trainer V2**!\n\n"
        "Use the menu below to navigate or type direct inputs like:\n"
        "• `132 Kilo` / `84.5 kg` / `132000 g`\n"
        "• `20 laps` or `Twenty Laps`\n"
        "• `My legs hurt` / `Meine Beine tun weh`"
    )
    await update.message.reply_text("Clearing old layout...", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(welcome_text, reply_markup=build_main_menu(), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_main":
        await query.edit_message_text("Main Menu:", reply_markup=build_main_menu())
    elif data == "menu_pool":
        is_hol = context.user_data.get('pool_holiday', False)
        is_rain = context.user_data.get('pool_rain', False)
        stats = get_pool_occupancy_stats()
        await query.edit_message_text(
            f"🏊 **Pool Status & Conditions**\n\n{stats}",
            reply_markup=build_pool_menu(is_hol, is_rain),
            parse_mode="Markdown"
        )
    elif data == "pool_toggle_holiday":
        context.user_data['pool_holiday'] = not context.user_data.get('pool_holiday', False)
        is_hol = context.user_data['pool_holiday']
        is_rain = context.user_data.get('pool_rain', False)
        stats = get_pool_occupancy_stats()
        await query.edit_message_text(
            f"🏊 **Pool Status & Conditions**\n\n{stats}",
            reply_markup=build_pool_menu(is_hol, is_rain),
            parse_mode="Markdown"
        )
    elif data == "pool_toggle_rain":
        context.user_data['pool_rain'] = not context.user_data.get('pool_rain', False)
        is_hol = context.user_data.get('pool_holiday', False)
        is_rain = context.user_data['pool_rain']
        stats = get_pool_occupancy_stats()
        await query.edit_message_text(
            f"🏊 **Pool Status & Conditions**\n\n{stats}",
            reply_markup=build_pool_menu(is_hol, is_rain),
            parse_mode="Markdown"
        )
    elif data == "menu_sport":
        await query.edit_message_text("🏋️ **Sport & Activity Tracking**", reply_markup=build_sport_menu(), parse_mode="Markdown")
    elif data == "menu_nutrients":
        await query.edit_message_text("☕ **Nutrients & Micro Toggle**\n\nRecord intake for healthy fats & magnesium synthesis:", reply_markup=build_nutrients_menu(), parse_mode="Markdown")
    elif data == "nutrient_yes":
        res = toggle_nutrient_log(1)
        await query.edit_message_text(f"☕ Cargill Cacao / Cashews: **{res}**", reply_markup=build_nutrients_menu(), parse_mode="Markdown")
    elif data == "nutrient_no":
        res = toggle_nutrient_log(0)
        await query.edit_message_text(f"☕ Cargill Cacao / Cashews: **{res}**", reply_markup=build_nutrients_menu(), parse_mode="Markdown")
    elif data == "menu_stats":
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT weight_kg, timestamp FROM weight_logs ORDER BY id DESC LIMIT 5", conn)
        conn.close()
        
        history_text = ""
        if not df.empty:
            history_text = "\n\n**Recent Entries:**\n" + "\n".join([f"• `{row['weight_kg']} kg` ({row['timestamp'][:16]})" for _, row in df.iterrows()])
            
        await query.edit_message_text(
            f"📊 **Stats & Measures**{history_text}\n\n_Type your weight anytime (e.g., '84.5 kg')._",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    elif data == "menu_coach":
        await query.edit_message_text("🤖 **Ollama AI Coach**\n\n_Coach module active. Video transcription pipeline available in Step 7._", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]), parse_mode="Markdown")
    else:
        await query.edit_message_text(f"Action logged: `{data}`", reply_markup=build_main_menu(), parse_mode="Markdown")

async def text_input_parser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip().lower()

    # 1. Kilogram Weight Logging
    kg_pattern = r'([\d\.,\s]+)\s*(kg|kilos|kilo|kilogram|kilograms|weighed)'
    kg_match = re.search(kg_pattern, text)
    if kg_match:
        try:
            val = clean_number(kg_match.group(1))
            daily_avg, ewma = save_weight_and_get_ewma(val)
            reply = (
                f"⚖️ **Weight Logged Successfully!**\n\n"
                f"• Raw Input: `{val:.1f} kg`\n"
                f"• Today's Average: `{daily_avg:.1f} kg`\n"
                f"• **7-Day EWMA Trend:** `{ewma:.2f} kg`"
            )
            await update.message.reply_text(reply, parse_mode="Markdown")
            return
        except ValueError:
            pass

    # 2. Gram Weight Logging -> Auto-converts to kg
    gram_pattern = r'([\d\.,\s]+)\s*(g|gram|gramm|grams)'
    gram_match = re.search(gram_pattern, text)
    if gram_match:
        try:
            raw_grams = clean_number(gram_match.group(1))
            val_kg = raw_grams / 1000.0
            daily_avg, ewma = save_weight_and_get_ewma(val_kg)
            reply = (
                f"⚖️ **Weight Logged Successfully!** ({raw_grams:.0f} g converted)\n\n"
                f"• Raw Input: `{val_kg:.1f} kg`\n"
                f"• Today's Average: `{daily_avg:.1f} kg`\n"
                f"• **7-Day EWMA Trend:** `{ewma:.2f} kg`"
            )
            await update.message.reply_text(reply, parse_mode="Markdown")
            return
        except ValueError:
            pass

    # 3. Swim Laps Logging
    swim_words_pattern = r'(' + '|'.join(WORD_TO_NUM.keys()) + r'|\d+)\s*(laps|lap|swam|bahnen|bahn)'
    swim_match = re.search(swim_words_pattern, text)
    if swim_match:
        raw_val = swim_match.group(1)
        laps_count = WORD_TO_NUM.get(raw_val, raw_val)
        await update.message.reply_text(f"🏊 Parsed Swimming Entry: **{laps_count} laps**.", parse_mode="Markdown")
        return

    # 4. Soreness Detection
    soreness_keywords = ['hurt', 'sore', 'weh', 'wehe', 'schmerz', 'muskelkater', 'neck', 'leg', 'arm', 'back']
    if any(keyword in text for keyword in soreness_keywords):
        await update.message.reply_text("🩹 **Soreness Recorded!** Universal Soreness Lock trigger activated.", parse_mode="Markdown")
        return

    # Default fallback
    await update.message.reply_text("Command not recognized.", reply_markup=build_main_menu())

def main() -> None:
    init_db()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token or not token.strip():
        logger.error("TELEGRAM_BOT_TOKEN is missing!")
        return

    app = Application.builder().token(token.strip()).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_parser))

    logger.info("Starting Fitness Trainer V2 Bot...")
    app.run_polling()

if __name__ == "__main__":
    main()

