import re

def clean_number(num_str: str) -> float:
    """Cleans up numeric inputs for float conversion."""
    num_str = num_str.strip()
    if '.' in num_str and ',' in num_str:
        num_str = num_str.replace('.', '').replace(',', '.')
    elif '.' in num_str:
        parts = num_str.split('.')
        if len(parts[-1]) == 3 and len(parts) > 1:
            num_str = num_str.replace('.', '')
    elif ',' in num_str:
        parts = num_str.split(',')
        if len(parts[-1]) == 3 and len(parts) > 1:
            num_str = num_str.replace(',', '')
        else:
            num_str = num_str.replace(',', '.')
    return float(num_str)

def parse_weight_input(text_lower: str) -> float | None:
    """Parses weight from text in kg or grams."""
    kg_pattern = r'([\d\.,\s]+)\s*(kg|kilos|kilo|kilogram|kilograms|weighed)'
    kg_match = re.search(kg_pattern, text_lower)
    if kg_match:
        try:
            return clean_number(kg_match.group(1))
        except ValueError:
            pass

    gram_pattern = r'([\d\.,\s]+)\s*(g|gram|gramm|grams)'
    gram_match = re.search(gram_pattern, text_lower)
    if gram_match:
        try:
            raw_grams = clean_number(gram_match.group(1))
            return raw_grams / 1000.0
        except ValueError:
            pass

    return None

def parse_soreness_input(text_lower: str) -> list[str] | None:
    """Parses muscle soreness or pain mentions."""
    body_parts_map = {
        'leg': 'legs', 'legs': 'legs', 'beine': 'legs', 'bein': 'legs',
        'knee': 'knees', 'knees': 'knees', 'knie': 'knees',
        'arm': 'arms', 'arms': 'arms', 'arme': 'arms', 'arm': 'arms',
        'shoulder': 'shoulders', 'shoulders': 'shoulders', 'schulter': 'shoulders', 'schultern': 'shoulders',
        'chest': 'chest', 'breast': 'chest', 'brust': 'chest', 'tits': 'chest', 'titties': 'chest', 'busen': 'chest', 'boobs': 'chest', 'man boobs': 'chest', 'männerbrust': 'chest',
        'neck': 'neck', 'nacken': 'neck',
        'stomach': 'abs/stomach', 'abs': 'abs/stomach', 'core': 'abs/stomach', 'bauch': 'abs/stomach',
        'back': 'back', 'rücken': 'back',
        'calf': 'calves', 'calves': 'calves', 'wade': 'calves', 'waden': 'calves',
        'glute': 'glutes', 'glutes': 'glutes', 'butt': 'glutes', 'po': 'glutes', 'arsch': 'glutes', 'hintern': 'glutes'
    }
    
    soreness_triggers = ['sore', 'hurt', 'hurts', 'pain', 'aching', 'stiff', 'weh', 'wehe', 'schmerz', 'schmerzen', 'muskelkater', 'steif']
    
    if any(trigger in text_lower for trigger in soreness_triggers):
        detected_parts = []
        for word, canonical_part in body_parts_map.items():
            if word in text_lower and canonical_part not in detected_parts:
                detected_parts.append(canonical_part)
        return detected_parts
        
    return None

