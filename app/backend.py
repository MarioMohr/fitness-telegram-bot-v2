import sqlite3
from datetime import datetime, date
import os
import pytz
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ENV_DB_URL = os.getenv("DATABASE_URL", "")
if "sqlite:///" in ENV_DB_URL:
    DB_PATH = ENV_DB_URL.replace("sqlite:///", "")
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "fitness.db")

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_local_now():
    return datetime.now(TIMEZONE)

def get_local_today():
    return get_local_now().date()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pool_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            occupancy TEXT NOT NULL,
            is_holiday INTEGER NOT NULL,
            is_raining INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            date_logged TEXT NOT NULL,
            weight_kg REAL NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(weight_logs)")
    columns = [col[1] for col in cursor.fetchall()]
    if "date_logged" not in columns:
        cursor.execute("ALTER TABLE weight_logs ADD COLUMN date_logged TEXT")
        cursor.execute("UPDATE weight_logs SET date_logged = substr(timestamp, 1, 10) WHERE date_logged IS NULL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nutrient_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_logged TEXT UNIQUE NOT NULL,
            taken INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS soreness_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            body_part TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS body_measures_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            chest_cm REAL,
            arms_cm REAL,
            waist_cm REAL,
            hip_cm REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def save_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_setting(key: str, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def save_target_weight(weight: float):
    save_setting("target_weight", str(weight))

def get_target_weight():
    val = get_setting("target_weight")
    if val is not None:
        try:
            return float(val)
        except ValueError:
            return None
    return None

def log_pool_status(occupancy: str, is_holiday: bool, is_raining: bool):
    conn = get_connection()
    cursor = conn.cursor()
    now_utc_str = datetime.now(pytz.utc).isoformat()
    cursor.execute("""
        INSERT INTO pool_logs (timestamp, occupancy, is_holiday, is_raining)
        VALUES (?, ?, ?, ?)
    """, (now_utc_str, occupancy, int(is_holiday), int(is_raining)))
    conn.commit()
    conn.close()

def get_pool_best_times() -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, occupancy FROM pool_logs")
    rows = cursor.fetchall()
    conn.close()

    days_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }

    stats = {i: {"total": 0, "empty_hours": {}} for i in range(7)}

    for row in rows:
        ts_str = row['timestamp']
        occ = row['occupancy'].lower()
        try:
            dt_utc = datetime.fromisoformat(ts_str)
            if dt_utc.tzinfo is None:
                dt_utc = pytz.utc.localize(dt_utc)
            dt_local = dt_utc.astimezone(TIMEZONE)
        except Exception:
            continue

        weekday = dt_local.weekday()
        stats[weekday]["total"] += 1

        if "empty" in occ:
            hour_str = dt_local.strftime("%H:00")
            stats[weekday]["empty_hours"][hour_str] = stats[weekday]["empty_hours"].get(hour_str, 0) + 1

    result_lines = []
    for day_idx in range(7):
        day_name = days_map[day_idx]
        total_count = stats[day_idx]["total"]
        empty_hours = stats[day_idx]["empty_hours"]

        if empty_hours:
            sorted_hours = sorted(empty_hours.items(), key=lambda x: x[1], reverse=True)
            top_hours = [h[0] for h in sorted_hours[:2]]
            best_str = ", ".join(top_hours)
        else:
            best_str = "No empty logs"

        result_lines.append(f"• {day_name} ({total_count}): {best_str}")

    return "\n".join(result_lines)

def save_weight_and_get_ewma(weight: float):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = get_local_now().isoformat()
    today_str = get_local_today().isoformat()

    cursor.execute("""
        INSERT INTO weight_logs (timestamp, date_logged, weight_kg)
        VALUES (?, ?, ?)
    """, (now_str, today_str, weight))
    conn.commit()

    df = pd.read_sql_query("SELECT date_logged, weight_kg FROM weight_logs ORDER BY timestamp ASC", conn)
    conn.close()

    today_weights = df[df['date_logged'] == today_str]['weight_kg']
    daily_avg = today_weights.mean()

    daily_df = df.groupby('date_logged')['weight_kg'].mean().reset_index()
    daily_df['ewma'] = daily_df['weight_kg'].ewm(span=7, adjust=False).mean()
    
    latest_ewma = daily_df['ewma'].iloc[-1]

    return daily_avg, latest_ewma

def get_latest_weight():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT weight_kg FROM weight_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row and row['weight_kg'] is not None:
        return row['weight_kg']
    return None

def get_recent_weight_logs(limit: int = 14):
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT date_logged, weight_kg FROM weight_logs ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df

def toggle_nutrient_log(taken: int):
    conn = get_connection()
    cursor = conn.cursor()
    today_str = get_local_today().isoformat()

    cursor.execute("""
        INSERT INTO nutrient_logs (date_logged, taken)
        VALUES (?, ?)
        ON CONFLICT(date_logged) DO UPDATE SET taken=excluded.taken
    """, (today_str, taken))
    conn.commit()
    conn.close()
    return "Marked as Taken" if taken == 1 else "Marked as Not Taken"

def save_soreness_log(body_parts: list):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = get_local_now().isoformat()
    for part in body_parts:
        cursor.execute("""
            INSERT INTO soreness_logs (timestamp, body_part)
            VALUES (?, ?)
        """, (now_str, part))
    conn.commit()
    conn.close()

def save_body_measures(chest=None, arms=None, waist=None, hip=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT chest_cm, arms_cm, waist_cm, hip_cm FROM body_measures_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    last_chest = row['chest_cm'] if row else None
    last_arms = row['arms_cm'] if row else None
    last_waist = row['waist_cm'] if row else None
    last_hip = row['hip_cm'] if row else None

    new_chest = chest if chest is not None else last_chest
    new_arms = arms if arms is not None else last_arms
    new_waist = waist if waist is not None else last_waist
    new_hip = hip if hip is not None else last_hip

    now_str = get_local_now().isoformat()
    cursor.execute("""
        INSERT INTO body_measures_logs (timestamp, chest_cm, arms_cm, waist_cm, hip_cm)
        VALUES (?, ?, ?, ?, ?)
    """, (now_str, new_chest, new_arms, new_waist, new_hip))
    
    conn.commit()
    conn.close()
    return new_chest, new_arms, new_waist, new_hip

def get_latest_body_measures():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chest_cm, arms_cm, waist_cm, hip_cm FROM body_measures_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return row['chest_cm'], row['arms_cm'], row['waist_cm'], row['hip_cm']
    
    return None, None, None, None

