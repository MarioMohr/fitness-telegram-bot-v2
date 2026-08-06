import re

def convert_words_to_digits(text: str) -> str:
    """Converts written english numbers and digit sequences into numeric strings."""
    word_digits = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
    }
    tens = {
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
    }
    teens = {
        'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
        'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19
    }
    
    words = text.lower().replace('-', ' ').split()
    new_words = []
    i = 0
    
    while i < len(words):
        w = words[i].strip(',.')
        
        if w in word_digits:
            digit_seq = ""
            while i < len(words) and words[i].strip(',.') in word_digits:
                digit_seq += word_digits[words[i].strip(',.')]
                i += 1
            new_words.append(digit_seq)
            continue
            
        if w in word_digits and i + 1 < len(words) and words[i+1].strip(',.') == 'hundred':
            hundreds_val = int(word_digits[w]) * 100
            i += 2
            remainder = 0
            if i < len(words) and words[i].strip(',.') in tens:
                remainder += tens[words[i].strip(',.')]
                i += 1
                if i < len(words) and words[i].strip(',.') in word_digits:
                    remainder += int(word_digits[words[i].strip(',.')])
                    i += 1
            elif i < len(words) and words[i].strip(',.') in teens:
                remainder += teens[words[i].strip(',.')]
                i += 1
            elif i < len(words) and words[i].strip(',.') in word_digits:
                remainder += int(word_digits[words[i].strip(',.')])
                i += 1
            new_words.append(str(hundreds_val + remainder))
            continue

        if w in tens:
            val = tens[w]
            if i + 1 < len(words) and words[i+1].strip(',.') in word_digits:
                val += int(word_digits[words[i+1].strip(',.')])
                i += 2
            else:
                i += 1
            new_words.append(str(val))
            continue

        if w in teens:
            new_words.append(str(teens[w]))
            i += 1
            continue

        new_words.append(words[i])
        i += 1
        
    return " ".join(new_words)

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

def parse_weight_input(text_raw: str) -> float | None:
    """Parses weight from text in kg or grams."""
    text_lower = convert_words_to_digits(text_raw)
    
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

def parse_soreness_input(text_raw: str) -> list[str] | None:
    """Parses muscle soreness or pain mentions."""
    text_lower = convert_words_to_digits(text_raw)
    
    body_parts_map = {
        'leg': 'legs', 'legs': 'legs',
        'knee': 'knees', 'knees': 'knees',
        'arm': 'arms', 'arms': 'arms',
        'shoulder': 'shoulders', 'shoulders': 'shoulders',
        'chest': 'chest', 'breast': 'chest', 'tits': 'chest', 'boobs': 'chest',
        'neck': 'neck',
        'stomach': 'abs/stomach', 'abs': 'abs/stomach', 'core': 'abs/stomach', 'waist': 'abs/stomach',
        'back': 'back',
        'calf': 'calves', 'calves': 'calves',
        'glute': 'glutes', 'glutes': 'glutes', 'butt': 'glutes'
    }
    
    soreness_triggers = ['sore', 'hurt', 'hurts', 'pain', 'aching', 'stiff']
    
    if any(trigger in text_lower for trigger in soreness_triggers):
        detected_parts = []
        for word, canonical_part in body_parts_map.items():
            if word in text_lower and canonical_part not in detected_parts:
                detected_parts.append(canonical_part)
        return detected_parts
        
    return None

def parse_body_measures_input(text_raw: str) -> dict[str, float]:
    """Parses chest, arms, waist/stomach, and hip measurements in any order."""
    text_lower = convert_words_to_digits(text_raw)
    results = {}
    
    keywords = {
        'chest': r'(chest|breast)',
        'arms': r'(arms|arm|biceps)',
        'waist': r'(waist|stomach|belly)',
        'hip': r'(hip|hips)'
    }
    
    for key, kw_pattern in keywords.items():
        pattern_prefix = rf'{kw_pattern}\s*[:=,\s]*\s*([\d\.,]+)'
        pattern_suffix = rf'([\d\.,]+)\s*(?:cm)?\s*{kw_pattern}'
        
        match_prefix = re.search(pattern_prefix, text_lower)
        match_suffix = re.search(pattern_suffix, text_lower)
        
        if match_prefix:
            try:
                results[key] = clean_number(match_prefix.group(2))
            except ValueError:
                pass
        elif match_suffix:
            try:
                results[key] = clean_number(match_suffix.group(1))
            except ValueError:
                pass
                
    return results

