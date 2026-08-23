import sqlite3
import os

# Pfad gemäß deiner .env Variablen DATABASE_URL
DB_PATH = "/app/data/fitness.db"

def cleanup_workouts():
    if not os.path.exists(DB_PATH):
        print(f"Datenbank unter {DB_PATH} nicht gefunden.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Entfernt die Workout Tabelle komplett
    cursor.execute("DROP TABLE IF EXISTS workout_logs")
    
    # Führt eine Speicherbereinigung der Datenbank Datei durch
    cursor.execute("VACUUM")

    conn.commit()
    conn.close()
    print("Workout Daten erfolgreich gelöscht und Datenbank bereinigt.")

if __name__ == "__main__":
    cleanup_workouts()

