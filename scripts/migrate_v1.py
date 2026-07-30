import sqlite3
import os
from datetime import datetime

OLD_DB = "/app/data/fitness_v1.db"
NEW_DB = "/app/data/fitness.db"

def clean_timestamp(ts_str):
    try:
        # Schneidet Mikrosekunden und Zeitzone ab, damit Pandas es immer versteht
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str

def migrate_pool_data():
    if not os.path.exists(OLD_DB) or not os.path.exists(NEW_DB):
        print("❌ Datenbankpfade prüfen!")
        return

    old_conn = sqlite3.connect(OLD_DB)
    new_conn = sqlite3.connect(NEW_DB)
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()

    try:
        print("Lese V1-Pooldaten aus...")
        rows = old_cursor.execute("SELECT timestamp, status FROM pool_log").fetchall()
        
        migrated_rows = []
        for ts, status in rows:
            raw_status = str(status).strip().upper() if status else "FREI"
            clean_ts = clean_timestamp(ts)
            
            occupancy = "Empty"
            is_holiday = 0
            is_raining = 0
            recommendation = "Migrated from V1"

            if raw_status == "FREI":
                occupancy = "Empty"
            elif raw_status == "VOLL":
                occupancy = "Full"
            elif "TEIL" in raw_status or "PARTIAL" in raw_status:
                occupancy = "Partially Occupied"
            elif raw_status == "FEIERTAG" or "HOLIDAY" in raw_status:
                occupancy = "Empty"
                is_holiday = 1
            elif raw_status == "REGEN" or "RAIN" in raw_status:
                occupancy = "Empty"
                is_raining = 1

            migrated_rows.append((clean_ts, occupancy, is_holiday, is_raining, recommendation))

        new_cursor.executemany(
            "INSERT INTO pool_logs (timestamp, occupancy, is_holiday, is_raining, recommendation) VALUES (?, ?, ?, ?, ?)",
            migrated_rows
        )
        new_conn.commit()
        print(f"✅ ERFOLG! {len(migrated_rows)} Einträge sauber migriert.")

    except Exception as e:
        print(f"❌ Fehler: {e}")
    finally:
        old_conn.close()
        new_conn.close()

if __name__ == "__main__":
    migrate_pool_data()

