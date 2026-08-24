import os
import re
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from backend import (
    save_target_weight,
    get_target_weight,
    save_setting,
    get_setting,
    get_latest_weight
)

load_dotenv()

ENV_DB_URL = os.getenv("DATABASE_URL", "")
if "sqlite:///" in ENV_DB_URL:
    DB_PATH = ENV_DB_URL.replace("sqlite:///", "")
else:
    DB_PATH = os.getenv("DB_PATH", "/app/data/fitness.db")

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

class WeightService:
    def __init__(self):
        self.frame_modifiers = {
            'slim': 0.90,
            'normal': 1.00,
            'heavy': 1.10
        }
        self.look_modifiers = {
            'athletic': -3.0,
            'fit': 0.0,
            'fluffy': 4.0
        }

    def calculate_ideal_weight(self, height_cm: int, frame: str, look: str) -> float:
        base_weight = (height_cm - 100) * 0.9
        frame_mult = self.frame_modifiers.get(frame.lower(), 1.0)
        look_add = self.look_modifiers.get(look.lower(), 0.0)
        target_weight = (base_weight * frame_mult) + look_add
        return round(target_weight, 1)

    def format_calculation_result(self, height_cm: int, frame: str, look: str, calculated_weight: float) -> str:
        frame_labels = {
            'slim': 'Slim',
            'normal': 'Normal',
            'heavy': 'Heavy / Broad'
        }
        look_labels = {
            'athletic': 'Athletic (~12-15% BFP)',
            'fit': 'Fit / Normal (~16-20% BFP)',
            'fluffy': 'Soft / Fluffy (~21-25% BFP)'
        }

        frame_str = frame_labels.get(frame.lower(), frame)
        look_str = look_labels.get(look.lower(), look)
        min_range = round(calculated_weight - 2.5, 1)
        max_range = round(calculated_weight + 2.5, 1)

        return (
            "🧮 **Target Weight Calculation**\n\n"
            f"• **Height:** {height_cm} cm\n"
            f"• **Body Frame:** {frame_str}\n"
            f"• **Target Look:** {look_str}\n\n"
            f"🎯 **Calculated Target Weight:** **{calculated_weight} kg**\n"
            f"💡 *Optimal Range:* {min_range} kg - {max_range} kg\n\n"
            "Would you like to set this as your official target weight?"
        )

    def generate_weight_chart(self, output_path="/tmp/weight_chart.png", target_weight=None):
        if not os.path.exists(DB_PATH):
            return None

        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT timestamp, date_logged, weight_kg FROM weight_logs ORDER BY timestamp ASC", conn)
        conn.close()

        if df.empty:
            return None

        df['date_logged'] = pd.to_datetime(df['date_logged'])
        daily_df = df.groupby('date_logged')['weight_kg'].mean().reset_index()
        daily_df['ewma'] = daily_df['weight_kg'].ewm(span=7, adjust=False).mean()

        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
        fig.patch.set_facecolor('#0e0e12')
        ax.set_facecolor('#15151e')

        ax.scatter(daily_df['date_logged'], daily_df['weight_kg'], color='#a855f7', alpha=0.6, label='Daily Logs', s=30)
        ax.plot(daily_df['date_logged'], daily_df['ewma'], color='#ec4899', linewidth=2.5, label='7-Day Trend')

        if target_weight is not None:
            ax.axhline(y=target_weight, color='#22c55e', linestyle='--', linewidth=1.5, label=f'Goal ({target_weight} kg)')

        ax.set_title("Weight History & Trend", fontsize=14, pad=15, color='#ffffff', fontweight='bold')
        ax.set_ylabel("Weight (kg)", fontsize=11, color='#cccccc')
        ax.set_xlabel("Date", fontsize=11, color='#cccccc')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        ax.grid(True, linestyle='--', alpha=0.2, color='#ffffff')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#444444')
        ax.spines['bottom'].set_color('#444444')

        ax.legend(facecolor='#1e1e2d', edgecolor='none', labelcolor='#ffffff')

        plt.tight_layout()
        plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()

        return output_path

weight_service = WeightService()

def build_weight_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🔄 Refresh Calories")],
        [KeyboardButton("🎯 Set Target Weight"), KeyboardButton("⚡ Set Loss Speed")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_frame_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Slim")],
        [KeyboardButton("Normal")],
        [KeyboardButton("Heavy / Broad")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_look_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Athletic")],
        [KeyboardButton("Fit / Normal")],
        [KeyboardButton("Soft / Fluffy")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_confirm_target_menu(calculated_weight: float) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Yes"), KeyboardButton("No")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_speed_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("0.5 kg / week"), KeyboardButton("1.0 kg / week")],
        [KeyboardButton("1.5 kg / week"), KeyboardButton("2.0 kg / week")],
        [KeyboardButton("Custom Pace"), KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_today_burned_calories() -> float:
    if not os.path.exists(DB_PATH):
        return 0.0

    now_local = datetime.now(TIMEZONE)
    today_str = now_local.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT active_calories, resting_calories FROM daily_energy_logs WHERE date_str = ?", (today_str,))
    row = cur.fetchone()

    total_cals = 0.0
    if row:
        active = float(row[0]) if row[0] is not None else 0.0
        resting = float(row[1]) if row[1] is not None else 0.0
        total_cals = active + resting

    conn.close()
    return total_cals

def get_weekly_burned_calories() -> float:
    if not os.path.exists(DB_PATH):
        return 0.0

    now_local = datetime.now(TIMEZONE)
    start_of_week = (now_local - timedelta(days=now_local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    weekly_total = 0.0
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")

        cur.execute("SELECT active_calories, resting_calories FROM daily_energy_logs WHERE date_str = ?", (day_str,))
        row = cur.fetchone()

        if row:
            active = float(row[0]) if row[0] is not None else 0.0
            resting = float(row[1]) if row[1] is not None else 0.0
            weekly_total += (active + resting)

    conn.close()
    return weekly_total

def calculate_progress_summary() -> str:
    current_weight = get_latest_weight()
    target_weight = get_target_weight()
    speed_str = get_setting("weekly_loss_target_kg", "1.0")
    
    try:
        weekly_target_kg = float(speed_str)
    except ValueError:
        weekly_target_kg = 1.0

    weekly_calorie_goal = weekly_target_kg * 7700.0
    daily_calorie_goal = weekly_calorie_goal / 7.0

    burned_this_week = get_weekly_burned_calories()
    burned_today = get_today_burned_calories()

    remaining_week = max(0.0, weekly_calorie_goal - burned_this_week)
    remaining_today = max(0.0, daily_calorie_goal - burned_today)

    msg = (
        f"⚡ **Calorie Targets Overview** ({weekly_target_kg} kg/week goal)\n\n"
        f"📅 **Daily Target:**\n"
        f"• **Goal:** {int(daily_calorie_goal)} kcal / day\n"
        f"• **Burned Today:** {int(burned_today)} kcal\n"
        f"• **Remaining Today:** {int(remaining_today)} kcal\n\n"
        f"🗓️ **Weekly Target:**\n"
        f"• **Goal:** {int(weekly_calorie_goal)} kcal / week\n"
        f"• **Burned This Week:** {int(burned_this_week)} kcal\n"
        f"• **Remaining This Week:** {int(remaining_week)} kcal\n"
    )

    if current_weight and target_weight:
        diff = round(current_weight - target_weight, 1)
        if diff <= 0:
            msg += f"\n🎉 **Target weight of {target_weight} kg already reached!**"
        else:
            weeks_needed = round(diff / weekly_target_kg, 1)
            days_needed = int(round(weeks_needed * 7))
            
            msg += (
                f"\n📊 **Overall Weight Status:**\n"
                f"• **Current Weight:** {current_weight} kg\n"
                f"• **Target Weight:** {target_weight} kg ({diff} kg remaining)\n"
                f"• **Estimated Time:** ~{weeks_needed} weeks ({days_needed} days)\n"
            )

    return msg

async def handle_weight_command(update: Update, context: ContextTypes.DEFAULT_TYPE, main_menu_builder) -> bool:
    text = update.message.text.strip()
    text_lower = text.lower()
    calc_step = context.user_data.get('calc_step')

    if text_lower in ["weight", "⚖️ weight", "🔄 refresh calories", "refresh calories"]:
        target_w = context.user_data.get('target_weight')
        if target_w is None:
            target_w = get_target_weight()
            if target_w is not None:
                context.user_data['target_weight'] = target_w

        chart_path = weight_service.generate_weight_chart(target_weight=target_w)
        keyboard = build_weight_menu()
        
        progress_summary = calculate_progress_summary()

        caption_msg = (
            "⚖️ **WEIGHT MODULE**\n\n"
            "Log your weight anytime by sending direct inputs like:\n"
            "• 92 KG\n"
            "• 84.5 kg\n\n"
            f"{progress_summary}"
        )

        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption_msg,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        else:
            await update.message.reply_text(
                caption_msg,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return True

    if text_lower in ["🎯 set target weight", "set target weight"]:
        context.user_data['calc_step'] = 'frame'
        await update.message.reply_text(
            "🧮 **Step 1:** Select your body frame type:",
            parse_mode="Markdown",
            reply_markup=build_frame_menu()
        )
        return True

    if text_lower == "⚡ set loss speed":
        context.user_data['calc_step'] = 'select_speed'
        await update.message.reply_text(
            "⚡ **Select Weight Loss Speed Target**\n\nHow many kg do you want to lose per week?",
            parse_mode="Markdown",
            reply_markup=build_speed_menu()
        )
        return True

    if calc_step == 'select_speed':
        speed_mapping = {
            "0.5 kg / week": 0.5,
            "1.0 kg / week": 1.0,
            "1.5 kg / week": 1.5,
            "2.0 kg / week": 2.0
        }
        
        if text_lower in [k.lower() for k in speed_mapping.keys()]:
            selected_val = next(v for k, v in speed_mapping.items() if k.lower() == text_lower)
            save_setting("weekly_loss_target_kg", str(selected_val))
            context.user_data['calc_step'] = None
            await update.message.reply_text(
                f"✅ Weight loss goal set to **{selected_val} kg per week**!",
                parse_mode="Markdown",
                reply_markup=build_weight_menu()
            )
            return True
        elif text_lower == "custom pace":
            context.user_data['calc_step'] = 'awaiting_custom_speed'
            await update.message.reply_text("Please enter your weekly goal in kg (e.g., 2.5 kg):")
            return True

    if calc_step == 'awaiting_custom_speed':
        val_match = re.search(r'\b([0-9](?:[\.,][0-9])?)\b', text_lower)
        if val_match:
            custom_speed = float(val_match.group(0).replace(',', '.'))
            save_setting("weekly_loss_target_kg", str(custom_speed))
            context.user_data['calc_step'] = None
            await update.message.reply_text(
                f"✅ Custom weight loss goal set to **{custom_speed} kg per week**!",
                parse_mode="Markdown",
                reply_markup=build_weight_menu()
            )
            return True
        else:
            await update.message.reply_text("Invalid input.", reply_markup=build_weight_menu())
            context.user_data['calc_step'] = None
            return True

    if calc_step == 'frame' and text_lower in ["slim", "normal", "heavy / broad", "heavy"]:
        frame_val = "heavy" if "heavy" in text_lower else text_lower
        context.user_data['calc_frame'] = frame_val
        context.user_data['calc_step'] = 'look'
        await update.message.reply_text(
            "🧮 **Step 2:** Select your desired target look:",
            parse_mode="Markdown",
            reply_markup=build_look_menu()
        )
        return True

    if calc_step == 'look' and text_lower in ["athletic", "fit / normal", "soft / fluffy", "fit", "fluffy"]:
        look_val = "fit" if "fit" in text_lower else ("fluffy" if "fluffy" in text_lower else text_lower)
        frame_val = context.user_data.get('calc_frame', 'normal')
        height_val = context.user_data.get('user_height', 175)

        target_weight = weight_service.calculate_ideal_weight(height_val, frame_val, look_val)
        context.user_data['pending_calculated_weight'] = target_weight
        context.user_data['calc_step'] = 'confirm_target'

        result_text = weight_service.format_calculation_result(height_val, frame_val, look_val, target_weight)
        await update.message.reply_text(
            result_text,
            parse_mode="Markdown",
            reply_markup=build_confirm_target_menu(target_weight)
        )
        return True

    if calc_step == 'confirm_target':
        pending_val = context.user_data.get('pending_calculated_weight')

        if text_lower in ["yes", "ja"]:
            context.user_data['target_weight'] = pending_val
            save_target_weight(pending_val)
            context.user_data['calc_step'] = None
            context.user_data.pop('pending_calculated_weight', None)

            chart_path = weight_service.generate_weight_chart(target_weight=pending_val)
            caption_msg = f"🎯 Target weight set to **{pending_val} kg**!"

            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=caption_msg,
                        parse_mode="Markdown",
                        reply_markup=main_menu_builder()
                    )
            else:
                await update.message.reply_text(
                    caption_msg,
                    parse_mode="Markdown",
                    reply_markup=main_menu_builder()
                )
            return True

        if text_lower in ["no", "nein"]:
            context.user_data['calc_step'] = None
            context.user_data.pop('pending_calculated_weight', None)
            await update.message.reply_text("Process cancelled.", reply_markup=main_menu_builder())
            return True

        context.user_data['calc_step'] = None
        context.user_data.pop('pending_calculated_weight', None)
        await update.message.reply_text("Process cancelled.", reply_markup=main_menu_builder())
        return True

    return False

