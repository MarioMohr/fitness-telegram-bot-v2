import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fitness.db")

def generate_weight_chart(output_path="/tmp/weight_chart.png"):
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

