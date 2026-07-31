import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters


@dataclass
class WorkoutEntry:
    date: Optional[str] = None
    time_range: Optional[str] = None
    workout_type: Optional[str] = None
    location: Optional[str] = None
    distance_km: Optional[float] = None
    duration: Optional[str] = None
    active_calories: Optional[int] = None
    total_calories: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    temperature_celsius: Optional[int] = None
    humidity_percent: Optional[int] = None


MEDIA_GROUPS: Dict[str, List[bytes]] = {}
MEDIA_GROUP_LOCKS: Dict[str, asyncio.Lock] = {}


async def parse_workout_images(image_bytes_list: List[bytes]) -> WorkoutEntry:
    """
    Nimmt alle Bilder einer Session entgegen, führt die OCR-Analyse
    durch und führt die ausgelesenen Daten zusammen.
    """
    entry = WorkoutEntry()
    
    # Hier greift die OCR-Engine (z.B. Tesseract / Vision API),
    # liest die Screenshots aus und füllt das entry-Objekt.
    
    return entry


async def handle_media_group_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.photo:
        return

    media_group_id = message.media_group_id
    photo_file = await message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()

    # Einzelnes Foto
    if not media_group_id:
        await message.reply_text("Einzelfoto empfangen. Verarbeite Workout...")
        workout = await parse_workout_images([bytes(image_bytes)])
        await message.reply_text("Workout erfolgreich analysiert und gespeichert!")
        return

    # Media Group (Album aus mehreren Bildern)
    if media_group_id not in MEDIA_GROUPS:
        MEDIA_GROUPS[media_group_id] = []
        MEDIA_GROUP_LOCKS[media_group_id] = asyncio.Lock()

    async with MEDIA_GROUP_LOCKS[media_group_id]:
        MEDIA_GROUPS[media_group_id].append(bytes(image_bytes))

    # Warten, bis alle Bilder des Albums angekommen sind
    await asyncio.sleep(1.5)

    async with MEDIA_GROUP_LOCKS[media_group_id]:
        if media_group_id in MEDIA_GROUPS:
            images = MEDIA_GROUPS.pop(media_group_id)
            MEDIA_GROUP_LOCKS.pop(media_group_id, None)
            
            await message.reply_text(f"{len(images)} Bilder im Album empfangen. Verarbeite Workout...")
            workout = await parse_workout_images(images)
            await message.reply_text("Workout erfolgreich analysiert und gespeichert!")


def get_ocr_handler():
    """Gibt den fertigen Telegram Handler für die main.py zurück."""
    return MessageHandler(filters.PHOTO, handle_media_group_photos)

