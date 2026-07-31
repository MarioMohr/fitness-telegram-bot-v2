import os
import sqlite3
import logging
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
DB_PATH = "/app/data/fitness.db"
TZ_NAME = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")

def get_local_now() -> datetime:
    """Returns current datetime in configured timezone."""
    try:
        return datetime.now(ZoneInfo(TZ_NAME))
    except Exception as e:
        logger.error(f"Error loading timezone {TZ_NAME}: {e}")
        return datetime.now()

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

def get_recent_weight_logs(limit: int = 5) -> pd.DataFrame:
    """Fetches the most recent weight entries."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT weight_kg, timestamp FROM weight_logs ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

