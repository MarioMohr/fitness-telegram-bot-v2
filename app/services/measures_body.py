import os
from PIL import Image, ImageDraw, ImageFont

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
        'hip': (68, 648)      # Etwas nach oben korrigiert für mittige Ausrichtung
    }

    draw.text(coords['chest'], str(chest), fill=text_color, font=font)
    draw.text(coords['arms'], str(arms), fill=text_color, font=font)
    draw.text(coords['hip'], str(hip), fill=text_color, font=font)
    draw.text(coords['waist'], str(waist), fill=text_color, font=font)

    img.save(output_path)
    return output_path

