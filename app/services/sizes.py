import os
import re
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from backend import save_body_measures, get_latest_body_measures, get_latest_weight
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

def generate_body_measurements_image(
    chest="--", 
    arms="--", 
    waist="--", 
    hip="--", 
    height="--", 
    weight="--",
    output_path="/tmp/rendered_body.jpg"
):
    base_path = "app/data/body_silhouette.jpg"
    
    if not os.path.exists(base_path):
        base_path = "data/body_silhouette.jpg"
        if not os.path.exists(base_path):
            base_path = "app/data/body_silhouette.png"
            if not os.path.exists(base_path):
                base_path = "data/body_silhouette.png"
                if not os.path.exists(base_path):
                    return None

    try:
        img = Image.open(base_path).convert("RGB")
    except Exception as e:
        print(f"Error loading image at {base_path}: {e}")
        return None

    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except IOError:
        font = ImageFont.load_default()

    text_color = (240, 230, 255)

    coords = {
        'weight': (323, 45),
        'height': (664, 45),
        'chest': (76, 334),   
        'arms': (787, 334),   
        'waist': (787, 705),
        'hip': (76, 748)
    }

    draw.text(coords['weight'], str(weight), fill=text_color, font=font)
    draw.text(coords['height'], str(height), fill=text_color, font=font)
    draw.text(coords['chest'], str(chest), fill=text_color, font=font)
    draw.text(coords['arms'], str(arms), fill=text_color, font=font)
    draw.text(coords['waist'], str(waist), fill=text_color, font=font)
    draw.text(coords['hip'], str(hip), fill=text_color, font=font)

    img.save(output_path, "JPEG", quality=92)
    return output_path

def get_body_image(user_height: int = 175):
    chest, arms, waist, hip = get_latest_body_measures()
    latest_w = get_latest_weight()

    chest_val = str(int(round(chest))) if chest is not None else "--"
    arms_val = str(int(round(arms))) if arms is not None else "--"
    waist_val = str(int(round(waist))) if waist is not None else "--"
    hip_val = str(int(round(hip))) if hip is not None else "--"
    height_val = str(user_height) if user_height is not None else "--"
    weight_val = str(int(round(latest_w))) if latest_w is not None else "--"

    return generate_body_measurements_image(
        chest=chest_val,
        arms=arms_val,
        waist=waist_val,
        hip=hip_val,
        height=height_val,
        weight=weight_val
    )

async def send_measures_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_height = context.user_data.get('user_height', 175)
    image_path = get_body_image(user_height=current_height)
    
    caption_text = (
        "📐 BODY MEASURES\n\n"
        "Please set your height in centimeters if not already set.\n"
        "• 180 cm\n"
        "• length 180\n"
        "• size 180\n\n"
        "Adjust measurements using the menu buttons below.\n"
        "Or set them manually like:\n"
        "• 131 Chest\n"
        "• Stomach -3"
    )
    
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

    if text_lower in ["📐 measures", "measures", "sizes"]:
        await send_measures_overview(update, context)
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

        current_chest = float(chest) if chest is not None else 0.0
        current_arms = float(arms) if arms is not None else 0.0
        current_waist = float(waist) if waist is not None else 0.0
        current_hip = float(hip) if hip is not None else 0.0

        if part_name == "chest":
            current_chest += delta
        elif part_name == "arms":
            current_arms += delta
        elif part_name == "waist":
            current_waist += delta
        elif part_name == "hip":
            current_hip += delta

        save_body_measures(chest=current_chest, arms=current_arms, waist=current_waist, hip=current_hip)
        await send_measures_overview(update, context)
        return True

    is_height_keyword = any(kw in text_lower for kw in ["length", "size", "height", "cm"])

    if is_height_keyword:
        height_match = re.search(r'\b(1[4-9][0-9]|2[0-2][0-9])\b', text_lower)
        if height_match:
            new_height = int(height_match.group(1))
            context.user_data['user_height'] = new_height
            
            await update.message.reply_text(
                f"📏 Height updated to **{new_height} cm**!",
                parse_mode="Markdown"
            )
            await send_measures_overview(update, context)
            return True

    parsed_measures = parse_body_measures_input(text)
    if parsed_measures:
        c = parsed_measures.get('chest')
        a = parsed_measures.get('arms')
        w = parsed_measures.get('waist')
        h = parsed_measures.get('hip')
        
        new_c, new_a, new_w, new_h = save_body_measures(chest=c, arms=a, waist=w, hip=h)
        
        current_height = context.user_data.get('user_height', 175)
        reply = (
            "📐 Body Measurements Recorded!\n\n"
            f"• Height: {current_height} cm\n"
            f"• Chest: {int(round(new_c)) if new_c is not None else 'N/A'} cm\n"
            f"• Arms: {int(round(new_a)) if new_a is not None else 'N/A'} cm\n"
            f"• Waist: {int(round(new_w)) if new_w is not None else 'N/A'} cm\n"
            f"• Hip: {int(round(new_h)) if new_h is not None else 'N/A'} cm"
        )
        await update.message.reply_text(reply, reply_markup=build_measures_menu())
        return True

    return False

