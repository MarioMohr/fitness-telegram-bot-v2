import os
import sqlite3
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging konfigurieren
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

DB_PATH = "/app/data/fitness.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Erstes Test-Schema anlegen
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR REPLACE INTO system_info (key, value) VALUES ('version', '2.0')")
    conn.commit()
    conn.close()
    logger.info("Datenbank erfolgreich initialisiert.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Fitness Container v2 ist einsatzbereit!")

def main():
    init_db()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "DEIN_TELEGRAM_BOT_TOKEN_AUS_V1":
        logger.error("Kein gültiger TELEGRAM_BOT_TOKEN in der .env gefunden!")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))

    logger.info("Bot wird gestartet...")
    app.run_polling()

if __name__ == "__main__":
    main()

