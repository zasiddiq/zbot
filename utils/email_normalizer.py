from typing import Optional


class EmailNormalizer:
    """Utilities for normalizing email addresses."""

    @staticmethod
    def normalize(email: str) -> Optional[str]:
        """
        Normalize an email address to lowercase.

        Args:
            email: Email address string

        Returns:
            Normalized email in lowercase, or None if invalid.
        """
        if not email:
            return None

        email = email.strip().lower()
        if "@" not in email:
            return None

        return email

