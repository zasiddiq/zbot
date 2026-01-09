import time
from typing import Optional

from zbot.config import (
    BOT_OUT_PREFIX,
    BOT_PREFIX,
    COOLDOWN_SECONDS,
    POLL_SECONDS,
    logger,
)
from zbot.db.messages import MessagesDatabase
from zbot.services.message_sender import MessageSender
from zbot.services.openai_client import OpenAIClient
from zbot.utils.message_decoder import MessageDecoder


class iMessageBot:
    """Main bot class that monitors and responds to messages."""

    def __init__(
        self,
        chat_id: int,
        chat_name: str,
        ai_client: OpenAIClient,
        db: MessagesDatabase,
    ):
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.ai_client = ai_client
        self.db = db

        self.last_seen_id: Optional[int] = None
        self.last_debug_id: Optional[int] = None
        self.last_reply_time = 0.0

    def initialize(self) -> None:
        """Initialize bot state from latest message."""
        rows = self.db.fetch_messages(self.chat_id, limit=1)
        if rows:
            self.last_seen_id = int(rows[0]["msg_id"])
            logger.info(
                "Initialized last_seen_id=%s (won't respond to old messages)",
                self.last_seen_id,
            )
        else:
            logger.info("No existing messages in chat")

    def should_respond(self, msg_id: int, text: str, from_me: int) -> bool:
        """
        Determine if bot should respond to a message.
        """
        # Don't respond to empty messages
        if not text:
            return False

        # Don't respond to bot's own messages
        if text.startswith(BOT_OUT_PREFIX):
            return False

        # Only respond to messages starting with trigger prefix
        if not text.lower().startswith(BOT_PREFIX.lower()):
            return False

        # Cooldown check
        now = time.time()
        if now - self.last_reply_time < COOLDOWN_SECONDS:
            return False

        return True

    def extract_prompt(self, text: str) -> str:
        """Extract user prompt from message text (remove trigger prefix)."""
        prefix_len = len(BOT_PREFIX)
        return text[prefix_len:].strip()

    def send_reply(self, reply: str) -> bool:
        """
        Send a reply message to the chat.
        """
        outgoing = BOT_OUT_PREFIX + reply

        try:
            # Use handle method for phone/email, chat name for groups
            if self.chat_name.startswith("+") or "@" in self.chat_name:
                MessageSender.send_to_handle(self.chat_name, outgoing)
            else:
                MessageSender.send_to_chat_by_name(self.chat_name, outgoing)

            logger.info("Sent message ✅")
            return True
        except Exception as e:
            logger.warning("Send failed: %s", e)
            return False

    def run(self) -> None:
        """Main bot loop - monitors chat and responds to triggers."""
        logger.info(
            "Bot running for chat_id=%s send_name=%r", self.chat_id, self.chat_name
        )
        logger.info("Trigger prefix: %s", BOT_PREFIX)

        # Set system message
        self.ai_client.set_system_message(
            "You are a helpful assistant in a group chat. "
            "Be as human sounding as possible and long winded."
        )

        self.initialize()

        try:
            while True:
                try:
                    rows = self.db.fetch_messages(self.chat_id, limit=30)
                    if not rows:
                        time.sleep(POLL_SECONDS)
                        continue

                    newest = rows[0]
                    msg_id = int(newest["msg_id"])
                    from_me = int(newest["is_from_me"])
                    text = MessageDecoder.extract_text(newest)

                    # Debug logging for new messages
                    if msg_id != self.last_debug_id:
                        ab_len = (
                            len(newest["attributedBody"])
                            if newest["attributedBody"]
                            else 0
                        )
                        logger.info(
                            "DEBUG msg_id=%s from_me=%s text_len=%s "
                            "attributedBody_len=%s text=%r",
                            msg_id,
                            from_me,
                            len(text),
                            ab_len,
                            text[:200],
                        )
                        self.last_debug_id = msg_id

                    # Check if message is already seen (skip old messages)
                    if self.last_seen_id is not None and msg_id <= self.last_seen_id:
                        time.sleep(POLL_SECONDS)
                        continue

                    # Mark message as seen before processing
                    self.last_seen_id = msg_id

                    # Check if we should respond (checks prefix, cooldown, etc.)
                    if not self.should_respond(msg_id, text, from_me):
                        time.sleep(POLL_SECONDS)
                        continue

                    # Extract prompt and get AI response
                    prompt = self.extract_prompt(text)
                    logger.info("Incoming TRIGGER (from_me=%s): %r", from_me, prompt)

                    reply = self.ai_client.chat(prompt)
                    logger.info("Outgoing: %r", reply[:200])

                    # Send reply
                    self.last_reply_time = time.time()
                    self.send_reply(reply)

                except KeyboardInterrupt:
                    logger.info("Stopping.")
                    break
                except Exception as e:
                    logger.exception("Loop error: %r", e)

                time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Stopping.")
        except Exception as e:
            logger.exception("Fatal error: %r", e)
            raise

