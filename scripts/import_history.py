import sqlite3
import os

DB_PATH = "/app/data/fitness.db"

# Historic weigh-in data
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
    ("2026-08-03 08:30:00', 133.0)
]

def run_import():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executemany(
        "INSERT INTO weight_logs (timestamp, weight_kg) VALUES (?, ?)",
        data
    )
    
    conn.commit()
    conn.close()
    print(f"Successfully imported {len(data)} weight entries into SQLite!")

if __name__ == "__main__":
    run_import()

