import argparse

from zbot.config import LIST_LIMIT
from zbot.contacts.manager import ContactsManager
from zbot.db.messages import MessagesDatabase
from zbot.services.openai_client import OpenAIClient
from zbot.ui.chat_picker import ChatPicker
from zbot.bot.imessage_bot import iMessageBot


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="iMessage GPT bot with Contacts name resolution"
    )
    parser.add_argument(
        "--hint",
        type=str,
        default=None,
        help="Filter chats by substring (name/identifier/contact)",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="Skip picker and run for this chat_id",
    )
    parser.add_argument(
        "--with-contacts",
        action="store_true",
        help="Resolve 1:1 phone/email to Contacts.app names",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=LIST_LIMIT,
        help="How many recent chats to show",
    )
    args = parser.parse_args()

    # Initialize components
    db = MessagesDatabase()
    contacts = ContactsManager()
    ai_client = OpenAIClient()

    # Select chat
    if args.chat_id is None:
        picker = ChatPicker(db, contacts)
        chosen_chat_id, _label = picker.pick(
            hint=args.hint,
            limit=args.limit,
            use_contacts=args.with_contacts,
        )
    else:
        chosen_chat_id = args.chat_id

    # Get chat name for sending
    chat_send_name = db.get_chat_name(chosen_chat_id)

    # Create and run bot
    bot = iMessageBot(chosen_chat_id, chat_send_name, ai_client, db)
    bot.run()


