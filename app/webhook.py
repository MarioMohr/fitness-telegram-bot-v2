import os
import sqlite3
import requests
from fastapi import FastAPI, HTTPException, Request

from services.weight import calculate_progress_summary

app = FastAPI(title="Fitness Bot Webhook")

DB_PATH = os.getenv("DB_PATH", "/app/data/fitness.db")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("ALLOWED_CHAT_ID")

def init_workout_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            workout_type TEXT,
            duration_minutes REAL,
            active_calories REAL,
            total_calories REAL,
            avg_heart_rate REAL,
            current_weight_kg REAL,
            raw_payload TEXT
        )
    """)
    conn.commit()
    conn.close()

init_workout_db()

def send_telegram_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram Token or Chat ID missing.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def parse_qty(metric):
    if not metric:
        return 0.0
    if isinstance(metric, dict):
        return metric.get("qty", 0.0)
    if isinstance(metric, list):
        return sum(item.get("qty", 0.0) for item in metric if isinstance(item, dict))
    return 0.0

def sum_metric(metric):
    total_kj = parse_qty(metric)
    return round(total_kj / 4.184, 1)

def avg_metric(metric):
    if isinstance(metric, dict):
        return round(metric.get("qty", 0.0), 1)
    if isinstance(metric, list):
        values = [item.get("qty", 0.0) for item in metric if isinstance(item, dict) and item.get("qty")]
        return round(sum(values) / len(values), 1) if values else 0.0
    return 0.0

@app.post("/webhook/workout")
async def receive_workout(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    workouts = payload.get("data", {}).get("workouts", [])
    if not workouts:
        workouts = payload if isinstance(payload, list) else [payload]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for w in workouts:
        if not isinstance(w, dict):
            continue

        workout_type = w.get("name", "Workout")
        
        duration = 0.0
        if "duration" in w:
            duration = round(w.get("duration", 0) / 60, 1)

        active_cal = sum_metric(w.get("activeEnergyBurned") or w.get("activeEnergy"))
        total_cal = sum_metric(w.get("totalEnergyBurned") or w.get("totalEnergy"))
        avg_hr = avg_metric(w.get("avgHeartRate") or w.get("heartRateData") or w.get("heartRate"))
        weight = 0.0

        cur.execute("""
            INSERT INTO workout_logs (workout_type, duration_minutes, active_calories, total_calories, avg_heart_rate, current_weight_kg, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (workout_type, duration, active_cal, total_cal, avg_hr, weight, str(w)))

        progress_msg = calculate_progress_summary(active_cal, workout_type)
        send_telegram_message(progress_msg)

    conn.commit()
    conn.close()

    return {"status": "success", "message": "Workouts processed"}

