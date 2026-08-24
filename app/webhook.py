import os
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException, Request
from dotenv import load_dotenv

from backend import save_or_update_daily_energy, get_local_today

load_dotenv()

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

app = FastAPI(title="Fitness Bot Webhook")

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
        
        # Da Summarize Data in der App aktiv ist, nehmen wir den Höchstwert (Tages-Gesamtwert)
        metric_val = 0.0
        if isinstance(qty_list, list) and len(qty_list) > 0:
            vals = [float(item.get("qty", 0.0)) for item in qty_list if isinstance(item, dict)]
            if vals:
                metric_val = max(vals)
        elif isinstance(metric.get("qty"), (int, float)):
            metric_val = float(metric.get("qty", 0.0))

        units = str(metric.get("units", "")).lower()
        if "kj" in units:
            metric_val = metric_val / 4.184

        if any(keyword in name for keyword in ["active", "active_energy", "active_calories"]):
            active_cals = max(active_cals, metric_val)
        elif any(keyword in name for keyword in ["basal", "resting", "resting_energy", "resting_calories"]):
            resting_cals = max(resting_cals, metric_val)

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

    today_str = get_local_today().isoformat()
    active_cals, resting_cals = extract_calories_from_payload(data)

    print(f"\n--- EMPFANGENE KALORIEN [{today_str}] ---")
    print(f"Aktive Kalorien: {active_cals} kcal")
    print(f"Ruhekalorien:   {resting_cals} kcal")
    print("---------------------------------------\n")

    # Übergabe an das Backend zum zentralen Speichern
    save_or_update_daily_energy(today_str, active_cals, resting_cals)

    return {"status": "success", "message": "Data processed successfully via backend"}

