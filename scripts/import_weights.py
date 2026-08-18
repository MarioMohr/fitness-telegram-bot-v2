import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

ENV_DB_URL = os.getenv("DATABASE_URL", "")
if "sqlite:///" in ENV_DB_URL:
    DB_PATH = ENV_DB_URL.replace("sqlite:///", "")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_PATH = os.path.join(BASE_DIR, "app", "data", "fitness.db")

APP_TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")

data = [
    ("2026-07-11 00:00:00", 136.0),
    ("2026-07-11 12:00:00", 134.0),
    ("2026-07-13 12:45:00", 133.0),
    ("2026-07-13 15:30:00", 134.0),
    ("2026-07-14 04:00:00", 135.0),
    ("2026-07-14 13:00:00", 134.0),
    ("2026-07-14 22:30:00", 134.0),
    ("2026-07-17 11:00:00", 134.0),
    ("2026-07-17 22:00:00", 134.0),
    ("2026-07-18 12:00:00", 134.0),
    ("2026-07-20 12:00:00", 134.0),
    ("2026-07-21 11:30:00", 134.0),
    ("2026-07-22 01:00:00", 135.0),
    ("2026-07-22 13:00:00", 133.0),
    ("2026-07-23 11:00:00", 134.0),
    ("2026-07-23 13:00:00", 134.0),
    ("2026-07-24 11:00:00", 134.0),
    ("2026-07-24 14:00:00", 133.0),
    ("2026-07-29 16:30:00", 132.0),
    ("2026-07-30 13:00:00", 132.0),
    ("2026-08-03 08:30:00", 133.0),
    ("2026-08-07 07:00:00", 132.0)
]

def run_import():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    try:
        local_tz = ZoneInfo(APP_TIMEZONE_STR)
        utc_tz = ZoneInfo("UTC")
    except Exception as e:
        print(f"Error loading timezone '{APP_TIMEZONE_STR}': {e}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            date_logged TEXT NOT NULL,
            weight_kg REAL NOT NULL
        )
    """)

    imported_count = 0

    for dt_str, weight in data:
        naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        local_dt = naive_dt.replace(tzinfo=local_tz)
        utc_dt = local_dt.astimezone(utc_tz)

        utc_timestamp = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
        date_logged = local_dt.strftime("%Y-%m-%d")

        cursor.execute(
            """
            INSERT INTO weight_logs (timestamp, date_logged, weight_kg)
            VALUES (?, ?, ?)
            """,
            (utc_timestamp, date_logged, float(weight))
        )
        imported_count += 1

    conn.commit()
    conn.close()

    print(f"Successfully imported {imported_count} entries into {DB_PATH} using timezone {APP_TIMEZONE_STR}!")

if __name__ == "__main__":
    run_import()

