import os
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException, Request
from dotenv import load_dotenv

from backend import save_or_update_daily_energy

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
        
        metric_total = 0.0
        if isinstance(qty_list, list):
            for item in qty_list:
                if isinstance(item, dict):
                    metric_total += float(item.get("qty", 0.0))
        elif isinstance(metric.get("qty"), (int, float)):
            metric_total = float(metric.get("qty", 0.0))

        units = str(metric.get("units", "")).lower()
        if "kj" in units:
            metric_total = metric_total / 4.184

        if any(keyword in name for keyword in ["active", "active_energy", "active_calories"]):
            active_cals = max(active_cals, metric_total)
        elif any(keyword in name for keyword in ["basal", "resting", "resting_energy", "resting_calories"]):
            resting_cals = max(resting_cals, metric_total)

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

    print(f"\n[WEBHOOK SYNC] {datetime.now(TIMEZONE).strftime('%H:%M:%S')} für Datum {today_str}")
    print(f"-> Empfangen Aktive Kalorien: {active_cals} kcal")
    print(f"-> Empfangen Ruhekalorien:   {resting_cals} kcal")
    print(f"-> Gesamtwert für Heute:    {round(active_cals + resting_cals, 1)} kcal\n")

    # Übergabe an das Backend zum zentralen Speichern
    save_or_update_daily_energy(today_str, active_cals, resting_cals)

    return {"status": "success", "message": "Data saved correctly via backend"}

