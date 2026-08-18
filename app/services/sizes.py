import os
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from backend import save_body_measures, get_latest_body_measures
from services.parser import parse_body_measures_input

def build_measures_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Chest -1"), KeyboardButton("Chest +1")],
        [KeyboardButton("Arms -1"), KeyboardButton("Arms +1")],
        [KeyboardButton("Waist -1"), KeyboardButton("Waist +1")],
        [KeyboardButton("Hip -1"), KeyboardButton("Hip +1")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def generate_body_measurements_image(chest="--", arms="--", waist="--", hip="--", output_path="/tmp/rendered_body.png"):
    base_path = "data/body_silhouette.jpg" 
    
    if not os.path.exists(base_path):
        base_path = "app/data/body_silhouette.jpg"
        if not os.path.exists(base_path):
            return None

    try:
        img = Image.open(base_path).convert("RGBA")
    except Exception as e:
        print(f"Error loading image at {base_path}: {e}")
        return None

    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except IOError:
        font = ImageFont.load_default()

    text_color = (240, 230, 255, 255)

    coords = {
        'chest': (72, 234),   
        'arms': (780, 234),   
        'waist': (780, 610),  
        'hip': (68, 648)
    }

    draw.text(coords['chest'], str(chest), fill=text_color, font=font)
    draw.text(coords['arms'], str(arms), fill=text_color, font=font)
    draw.text(coords['hip'], str(hip), fill=text_color, font=font)
    draw.text(coords['waist'], str(waist), fill=text_color, font=font)

    img.save(output_path)
    return output_path

def get_body_image():
    chest, arms, waist, hip = get_latest_body_measures()

    chest_val = str(int(round(chest))) if chest is not None else "--"
    arms_val = str(int(round(arms))) if arms is not None else "--"
    waist_val = str(int(round(waist))) if waist is not None else "--"
    hip_val = str(int(round(hip))) if hip is not None else "--"

    return generate_body_measurements_image(
        chest=chest_val,
        arms=arms_val,
        waist=waist_val,
        hip=hip_val
    )

async def send_measures_overview(update: Update):
    image_path = get_body_image()
    caption_text = "📐 BODY MEASURES\n\nAdjust measurements by using the menu below or type inputs directly anywhere, including bodypart and size in centimeters.\nExample: 134 Chest"
    
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption_text,
                reply_markup=build_measures_menu()
            )
    else:
        await update.message.reply_text(
            caption_text,
            reply_markup=build_measures_menu()
        )

async def handle_sizes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    text = update.message.text.strip()
    text_lower = text.lower()

    if text_lower in ["📐 measures", "measures"]:
        await send_measures_overview(update)
        return True

    measure_adjustments = {
        "chest -1": ("chest", -1.0),
        "chest +1": ("chest", 1.0),
        "arms -1": ("arms", -1.0),
        "arms +1": ("arms", 1.0),
        "waist -1": ("waist", -1.0),
        "waist +1": ("waist", 1.0),
        "hip -1": ("hip", -1.0),
        "hip +1": ("hip", 1.0),
    }

    if text_lower in measure_adjustments:
        part_name, delta = measure_adjustments[text_lower]
        chest, arms, waist, hip = get_latest_body_measures()

        c = (chest or 134.0) + delta if part_name == "chest" else chest
        a = (arms or 49.0) + delta if part_name == "arms" else arms
        w = (waist or 110.0) + delta if part_name == "waist" else waist
        h = (hip or 131.0) + delta if part_name == "hip" else hip

        save_body_measures(c, a, w, h)
        await send_measures_overview(update)
        return True

    parsed_measures = parse_body_measures_input(text)
    if parsed_measures:
        c = parsed_measures.get('chest')
        a = parsed_measures.get('arms')
        w = parsed_measures.get('waist')
        h = parsed_measures.get('hip')
        
        new_c, new_a, new_w, new_h = save_body_measures(c, a, w, h)
        
        reply = (
            "📐 Body Measurements Recorded!\n\n"
            f"• Chest: {int(round(new_c)) if new_c is not None else 'N/A'} cm\n"
            f"• Arms: {int(round(new_a)) if new_a is not None else 'N/A'} cm\n"
            f"• Waist: {int(round(new_w)) if new_w is not None else 'N/A'} cm\n"
            f"• Hip: {int(round(new_h)) if new_h is not None else 'N/A'} cm"
        )
        await update.message.reply_text(reply, reply_markup=build_measures_menu())
        return True

    return False

