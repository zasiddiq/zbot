from typing import Optional, Tuple, List

from zbot.config import LIST_LIMIT
from zbot.contacts.manager import ContactsManager, CONTACTS_AVAILABLE
from zbot.db.messages import MessagesDatabase


class ChatPicker:
    """Interactive chat selection interface."""

    def __init__(self, db: MessagesDatabase, contacts: ContactsManager):
        """
        Initialize chat picker.
        """
        self.db = db
        self.contacts = contacts

    def pick(
        self,
        hint: Optional[str] = None,
        limit: int = LIST_LIMIT,
        use_contacts: bool = False,
    ) -> Tuple[int, str]:
        """
        Interactive chat picker.
        """
        if use_contacts:
            self.contacts.build_lookup()
            if not CONTACTS_AVAILABLE:
                print(
                    "⚠️  Contacts framework not available. "
                    "Install: pyobjc-framework-Contacts"
                )

        rows: List = self.db.fetch_chats(limit=3000)

        # Build filtered list
        filtered = []
        hint_l = (hint or "").lower().strip()

        for row in rows:
            chat_id = int(row["chat_id"])
            display_name = (row["display_name"] or "")
            identifier = (row["chat_identifier"] or "")

            label = (
                self.contacts.format_chat_label(display_name, identifier)
                if use_contacts
                else (display_name or identifier or "(Unknown)")
            )

            if hint_l and not any(
                hint_l in s.lower() for s in [display_name, identifier, label]
            ):
                continue

            msg_id = self.db.get_latest_message_id(chat_id) or 0
            filtered.append((msg_id, chat_id, label))

        if not filtered:
            raise RuntimeError("No recent chats matched. Try a different --hint.")

        # Sort by most recent message
        filtered.sort(reverse=True, key=lambda x: x[0])
        shown = filtered[:limit]

        # Display options
        print("\nChoose a recent chat:\n")
        for i, (msg_id, chat_id, label) in enumerate(shown, start=1):
            print(f"{i:2d}) chat_id={chat_id:<6} last_msg={msg_id:<10}  name={label}")

        # Get user input
        while True:
            choice = input(f"\nEnter 1-{len(shown)} (or 'q' to quit): ").strip()

            if choice.lower() in ("q", "quit", "exit"):
                raise SystemExit(0)

            if not choice.isdigit():
                print("Please enter a number.")
                continue

            idx = int(choice)
            if 1 <= idx <= len(shown):
                _, chat_id, label = shown[idx - 1]
                return chat_id, label

            print("Out of range.")

