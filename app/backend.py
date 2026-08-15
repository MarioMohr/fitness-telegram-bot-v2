import sqlite3
from datetime import datetime, date
import os
import pytz
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "fitness.db")
TIMEZONE = pytz.timezone("Asia/Kuala_Lumpur")

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

    conn.commit()
    conn.close()

def log_pool_status(occupancy: str, is_holiday: bool, is_raining: bool):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = get_local_now().isoformat()
    cursor.execute("""
        INSERT INTO pool_logs (timestamp, occupancy, is_holiday, is_raining)
        VALUES (?, ?, ?, ?)
    """, (now_str, occupancy, int(is_holiday), int(is_raining)))
    conn.commit()
    conn.close()

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

    last_chest = row['chest_cm'] if row and row['chest_cm'] is not None else 134.0
    last_arms = row['arms_cm'] if row and row['arms_cm'] is not None else 49.0
    last_waist = row['waist_cm'] if row and row['waist_cm'] is not None else 110.0
    last_hip = row['hip_cm'] if row and row['hip_cm'] is not None else 131.0

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

    if row and any(v is not None for v in [row['chest_cm'], row['arms_cm'], row['waist_cm'], row['hip_cm']]):
        return row['chest_cm'], row['arms_cm'], row['waist_cm'], row['hip_cm']
    
    # Standardwerte initialisieren, falls Datenbank noch leer ist
    return save_body_measures(134.0, 49.0, 151.0, 131.0)

