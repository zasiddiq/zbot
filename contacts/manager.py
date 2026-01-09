from typing import Dict

try:
    from Contacts import (  # type: ignore
        CNContactStore,
        CNContactFetchRequest,
        CNContactGivenNameKey,
        CNContactFamilyNameKey,
        CNContactNicknameKey,
        CNContactPhoneNumbersKey,
        CNContactEmailAddressesKey,
    )

    CONTACTS_AVAILABLE = True
except Exception:
    CONTACTS_AVAILABLE = False

from config import logger
from utils.phone_normalizer import PhoneNormalizer
from utils.email_normalizer import EmailNormalizer


class ContactsManager:
    """Manages contact lookup using macOS Contacts framework."""

    def __init__(self):
        """Initialize contacts manager."""
        self.lookup: Dict[str, str] = {}

    def build_lookup(self) -> Dict[str, str]:
        """
        Build a lookup dictionary mapping normalized phone/email to contact names.
        """
        self.lookup = {}

        if not CONTACTS_AVAILABLE:
            return self.lookup

        store = CNContactStore.alloc().init()

        keys = [
            CNContactGivenNameKey,
            CNContactFamilyNameKey,
            CNContactNicknameKey,
            CNContactPhoneNumbersKey,
            CNContactEmailAddressesKey,
        ]
        req = CNContactFetchRequest.alloc().initWithKeysToFetch_(keys)

        def full_name(contact) -> str:
            """Extract full name from contact."""
            given = str(contact.givenName() or "").strip()
            family = str(contact.familyName() or "").strip()
            nick = str(contact.nickname() or "").strip()
            name = (given + " " + family).strip()
            return name or nick or "(No Name)"

        def handler(contact, _stop_ptr):
            """Process a contact and add to lookup."""
            name = full_name(contact)

            # Process phone numbers
            for labeled in list(contact.phoneNumbers() or []):
                try:
                    val = str(labeled.value().stringValue() or "")
                except Exception:
                    continue
                norm = PhoneNormalizer.normalize(val)
                if norm and norm not in self.lookup:
                    self.lookup[norm] = name

            # Process email addresses
            for labeled in list(contact.emailAddresses() or []):
                try:
                    val = str(labeled.value() or "")
                except Exception:
                    continue
                norm = EmailNormalizer.normalize(val)
                if norm and norm not in self.lookup:
                    self.lookup[norm] = name

        ok, err = store.enumerateContactsWithFetchRequest_error_usingBlock_(
            req, None, handler
        )
        if not ok:
            logger.warning("Could not enumerate contacts: %r", err)
            return {}

        return self.lookup

    def format_chat_label(
        self, display_name: str, chat_identifier: str
    ) -> str:
        """
        Format a chat label with contact name resolution.
        """
        dn = (display_name or "").strip()
        ci = (chat_identifier or "").strip()

        if dn:
            return dn

        # Try to resolve identifier as phone
        phone = PhoneNormalizer.normalize(ci)
        if phone and phone in self.lookup:
            return f"{self.lookup[phone]} ({phone})"

        # Try to resolve identifier as email
        email = EmailNormalizer.normalize(ci)
        if email and email in self.lookup:
            return f"{self.lookup[email]} ({email})"

        return ci or "(Unknown)"

