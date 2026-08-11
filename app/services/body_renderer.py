import os
from PIL import Image, ImageDraw, ImageFont

def generate_body_measurements_image(weight="--", height="175", chest="--", arms="--", waist="--", hip="--", output_path="/tmp/rendered_body.png"):
    base_path = "data/body_silhouette.png" 
    
    if not os.path.exists(base_path):
        base_path = "app/data/body_silhouette.png"
        if not os.path.exists(base_path):
            return None

    try:
        img = Image.open(base_path).convert("RGBA")
    except Exception as e:
        print(f"Error loading image at {base_path}: {e}")
        return None

    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except IOError:
        font = ImageFont.load_default()
        font_large = font

    text_color = (240, 230, 255, 255)

    coords = {
        'weight': (298, 42),       # Nach rechts rücken ohne .0
        'height': (655, 42),       # Passt (175 cm)
        'chest': (62, 330),        # Nach rechts rücken ohne .0
        'arms': (780, 330),        # Unverändert
        'hip': (58, 745),          # Weiter nach unten & rechts
        'waist': (795, 695)        # Unverändert
    }

    draw.text(coords['weight'], str(weight), fill=text_color, font=font_large)
    draw.text(coords['height'], "175", fill=text_color, font=font_large)
    draw.text(coords['chest'], str(chest), fill=text_color, font=font)
    draw.text(coords['hip'], str(hip), fill=text_color, font=font)
    draw.text(coords['arms'], str(arms), fill=text_color, font=font)
    draw.text(coords['waist'], str(waist), fill=text_color, font=font)

    img.save(output_path)
    return output_path

