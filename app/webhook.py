import os
import sqlite3
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException, Request
from dotenv import load_dotenv

load_dotenv()

ENV_DB_URL = os.getenv("DATABASE_URL", "")
if "sqlite:///" in ENV_DB_URL:
    DB_PATH = ENV_DB_URL.replace("sqlite:///", "")
else:
    DB_PATH = os.getenv("DB_PATH", "/app/data/fitness.db")

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

app = FastAPI(title="Fitness Bot Webhook")

def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_energy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_str TEXT UNIQUE,
            active_calories REAL DEFAULT 0,
            resting_calories REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def extract_calories_from_payload(payload: dict):
    active_cals = 0.0
    resting_cals = 0.0

    data_obj = payload.get("data", payload)
    if isinstance(data_obj, dict):
        metrics = data_obj.get("metrics", [])
    elif isinstance(data_obj, list):
        metrics = data_obj
    else:
        metrics = []

    for metric in metrics:
        if not isinstance(metric, dict):
            continue

        name = metric.get("name", "").lower()
        qty_list = metric.get("data", [])
        
        total_qty = 0.0
        if isinstance(qty_list, list):
            for item in qty_list:
                if isinstance(item, dict):
                    total_qty += float(item.get("qty", 0.0))
        elif isinstance(metric.get("qty"), (int, float)):
            total_qty = float(metric.get("qty", 0.0))

        units = str(metric.get("units", "")).lower()
        if "kj" in units:
            total_qty = total_qty / 4.184

        if any(keyword in name for keyword in ["active", "active_energy", "active_calories"]):
            active_cals += total_qty
        elif any(keyword in name for keyword in ["basal", "resting", "resting_energy", "resting_calories"]):
            resting_cals += total_qty

    if active_cals == 0.0 and "active_calories" in payload:
        active_cals = float(payload.get("active_calories", 0.0))
    if resting_cals == 0.0 and "resting_calories" in payload:
        resting_cals = float(payload.get("resting_calories", 0.0))

    return round(active_cals, 1), round(resting_cals, 1)

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    now_local = datetime.now(TIMEZONE)
    today_str = now_local.strftime("%Y-%m-%d")

    active_cals, resting_cals = extract_calories_from_payload(data)

    print(f"--- EMPFANGENE KALORIEN [{today_str}] ---")
    print(f"Aktive Kalorien: {active_cals} kcal")
    print(f"Ruhekalorien: {resting_cals} kcal")
    print("---------------------------------------")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO daily_energy_logs (date_str, active_calories, resting_calories, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(date_str) DO UPDATE SET
            active_calories = excluded.active_calories,
            resting_calories = excluded.resting_calories,
            updated_at = CURRENT_TIMESTAMP
    """, (today_str, active_cals, resting_cals))

    conn.commit()
    conn.close()

    return {"status": "success", "message": "Data processed successfully"}

