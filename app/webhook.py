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

def process_and_save_payload(payload: dict):
    daily_data = {}

    data_obj = payload.get("data", payload)
    days_list = data_obj if isinstance(data_obj, list) else [data_obj]

    for day_item in days_list:
        if not isinstance(day_item, dict):
            continue
            
        metrics = day_item.get("metrics", [])
        if not isinstance(metrics, list):
            continue

        for metric in metrics:
            if not isinstance(metric, dict):
                continue

            name = metric.get("name", "").lower()
            qty_list = metric.get("data", [])
            units = str(metric.get("units", "")).lower()

            if isinstance(qty_list, list):
                for entry in qty_list:
                    if not isinstance(entry, dict):
                        continue
                    
                    date_raw = entry.get("date") or entry.get("startDate") or day_item.get("date")
                    if date_raw:
                        date_str = str(date_raw)[:10]
                    else:
                        date_str = get_local_today().isoformat()

                    val = float(entry.get("qty", 0.0))
                    if "kj" in units:
                        val = val / 4.184

                    if date_str not in daily_data:
                        daily_data[date_str] = {"active": 0.0, "resting": 0.0}

                    if any(kw in name for kw in ["active", "active_energy", "active_calories"]):
                        daily_data[date_str]["active"] = max(daily_data[date_str]["active"], val)
                    elif any(kw in name for kw in ["basal", "resting", "resting_energy", "resting_calories"]):
                        daily_data[date_str]["resting"] = max(daily_data[date_str]["resting"], val)

    if not daily_data and ("active_calories" in payload or "resting_calories" in payload):
        today_str = get_local_today().isoformat()
        daily_data[today_str] = {
            "active": float(payload.get("active_calories", 0.0)),
            "resting": float(payload.get("resting_calories", 0.0))
        }

    for date_key, cals in daily_data.items():
        act = round(cals["active"], 1)
        rst = round(cals["resting"], 1)
        
        print(f"--- EMPFANGENE KALORIEN [{date_key}] ---")
        print(f"Aktive Kalorien: {act} kcal")
        print(f"Ruhekalorien:   {rst} kcal")
        print("---------------------------------------\n")
        
        save_or_update_daily_energy(date_key, act, rst)

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    process_and_save_payload(data)

    return {"status": "success", "message": "Data processed successfully via backend"}

