import os
from typing import Dict, Any, Optional

class GoalsService:
    def __init__(self):
        # Basis-Modifikatoren für die Berechnung
        self.frame_modifiers = {
            'slim': 0.90,      # -10% für zierlichen Körperbau
            'normal': 1.00,    # Standard
            'heavy': 1.10      # +10% für schweren / breiten Knochenbau
        }
        
        self.look_modifiers = {
            'athletic': -3.0,  # Geringerer KFA (ca. 12-15%)
            'fit': 0.0,        # Gesunder Normalbereich (ca. 16-20%)
            'fluffy': 4.0      # Gemütlicher Look (ca. 21-25%)
        }

    def calculate_ideal_weight(self, height_cm: int, frame: str, look: str) -> float:
        """
        Berechnet das ideale Zielgewicht basierend auf Höhe, Körperbau und Ziel-Look.
        """
        # Creff-Basisberechnung
        base_weight = (height_cm - 100) * 0.9
        
        frame_mult = self.frame_modifiers.get(frame.lower(), 1.0)
        look_add = self.look_modifiers.get(look.lower(), 0.0)
        
        target_weight = (base_weight * frame_mult) + look_add
        return round(target_weight, 1)

    def format_calculation_result(self, height_cm: int, frame: str, look: str, calculated_weight: float) -> str:
        """
        Erstellt die formatierte Textausgabe für das Berechnungsergebnis.
        """
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

        text = (
            "🧮 **Ideal Weight Calculation**\n\n"
            f"• **Height:** {height_cm} cm\n"
            f"• **Body Frame:** {frame_str}\n"
            f"• **Target Look:** {look_str}\n\n"
            f"🎯 **Recommended Target Weight:** **{calculated_weight} kg**\n"
            f"💡 *Optimal Range:* {min_range} kg - {max_range} kg\n\n"
            "Would you like to set this as your official target weight?"
        )
        return text

    def get_frame_keyboard_markup(self):
        """
        Gibt die Datenstruktur für die Body Frame Inline-Buttons zurück.
        """
        return [
            [{"text": "Slim", "callback_data": "goal_frame_slim"}],
            [{"text": "Normal", "callback_data": "goal_frame_normal"}],
            [{"text": "Heavy / Broad", "callback_data": "goal_frame_heavy"}],
            [{"text": "❌ Cancel", "callback_data": "goal_cancel"}]
        ]

    def get_look_keyboard_markup(self):
        """
        Gibt die Datenstruktur für die Target Look Inline-Buttons zurück.
        """
        return [
            [{"text": "Athletic", "callback_data": "goal_look_athletic"}],
            [{"text": "Fit / Normal", "callback_data": "goal_look_fit"}],
            [{"text": "Soft / Fluffy", "callback_data": "goal_look_fluffy"}],
            [{"text": "❌ Cancel", "callback_data": "goal_cancel"}]
        ]

    def get_result_keyboard_markup(self, weight: float):
        """
        Gibt die Bestätigungs-Buttons nach der Berechnung zurück.
        """
        return [
            [{"text": f"✅ Set {weight} kg as Goal", "callback_data": f"goal_set_{weight}"}],
            [{"text": "✏️ Custom Goal", "callback_data": "goal_custom"}],
            [{"text": "❌ Cancel", "callback_data": "goal_cancel"}]
        ]

# Singleton-Instanz für den einfachen Import
goals_service = GoalsService()


