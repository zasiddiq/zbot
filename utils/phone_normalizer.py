import re
from typing import Optional


class PhoneNormalizer:
    """Utilities for normalizing phone numbers to E.164 format."""

    E164ISH = re.compile(r"^\+?\d[\d\-\(\)\s]{6,}$")

    @staticmethod
    def normalize(phone: str) -> Optional[str]:
        """
        Normalize a phone number string to E.164 format.

        Args:
            phone: Phone number string (may contain formatting)

        Returns:
            Normalized phone number in E.164 format (e.g., "+19095551234"),
            or None if invalid.
        """
        if not phone:
            return None

        phone = phone.strip()
        if not PhoneNormalizer.E164ISH.match(phone):
            return None

        digits = re.sub(r"\D", "", phone)
        if not digits:
            return None

        # Heuristic: if it already had + or looks like full intl, keep +.
        # If it's 10 digits, assume US +1.
        if len(digits) == 10:
            return "+1" + digits
        if phone.startswith("+"):
            return "+" + digits
        # If 11 digits and starts with 1, treat as +1
        if len(digits) == 11 and digits.startswith("1"):
            return "+" + digits
        # Otherwise just +digits
        return "+" + digits

