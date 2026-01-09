import logging
import os

# Database path
CHAT_DB = os.path.expanduser("~/Library/Messages/chat.db")

# Bot configuration
BOT_PREFIX = "@zbot"
BOT_OUT_PREFIX = "🤖 "
MODEL = "gpt-4o-mini"

# Timing configuration
POLL_SECONDS = 2
COOLDOWN_SECONDS = 6
MAX_CONTEXT_MESSAGES = 20

# UI configuration
LIST_LIMIT = 30  # Number of chats shown in the picker

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s - %(message)s",
)
logger = logging.getLogger("imessage-bot")

