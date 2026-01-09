#!/usr/bin/env python3
"""
iMessage GPT Bot

A macOS bot that monitors iMessage chats, responds to messages prefixed with
a trigger (e.g., "@zbot"), and sends AI-generated replies using OpenAI's API.

Requirements:
- macOS (uses pyobjc for Contacts and Messages database access)
- OpenAI API key set in OPENAI_API_KEY environment variable
- Messages.app with chat.db database
"""

import os
import sqlite3
import time
import random
import subprocess
import logging
import argparse
import re
from typing import List, Optional, Dict, Tuple

import openai
from openai import OpenAI

# pyobjc (Messages decode)
from Foundation import (  # type: ignore
    NSData,
    NSUnarchiver,
)

# pyobjc (Contacts)
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


# ============================================================================
# CONFIGURATION
# ============================================================================

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
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
logger = logging.getLogger("imessage-bot")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

class PhoneNormalizer:
    """Utilities for normalizing phone numbers to E.164 format."""
    
    E164ish = re.compile(r"^\+?\d[\d\-\(\)\s]{6,}$")

    @staticmethod
    def normalize(phone: str) -> Optional[str]:
        """
        Normalize a phone number string to E.164 format.
        
        Args:
            phone: Phone number string (may contain formatting)
            
        Returns:
            Normalized phone number in E.164 format (e.g., "+19095551234"),
            or None if invalid
        """
        if not phone:
            return None
        
        phone = phone.strip()
        if not PhoneNormalizer.E164ish.match(phone):
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


class EmailNormalizer:
    """Utilities for normalizing email addresses."""
    
    @staticmethod
    def normalize(email: str) -> Optional[str]:
        """
        Normalize an email address to lowercase.
        
        Args:
            email: Email address string
            
        Returns:
            Normalized email in lowercase, or None if invalid
        """
        if not email:
            return None
        
        email = email.strip().lower()
        if "@" not in email:
            return None
        
        return email


class MessageDecoder:
    """Utilities for decoding message text from Messages database."""
    
    # Blacklist of common strings found in attributedBody that aren't message text
    BLACKLIST = {
        "streamtyped",
        "NSAttributedString",
        "NSObject",
        "NSString",
        "__kIMMessagePartAttributeName"
    }
    
    @staticmethod
    def _scan_printable(blob: bytes, min_len: int = 4) -> str:
        """
        Scan binary data for printable ASCII sequences.
        
        Args:
            blob: Binary data to scan
            min_len: Minimum length of printable sequence to extract
            
        Returns:
            Longest printable string found
        """
        runs = []
        cur = bytearray()
        
        for b in blob:
            if 32 <= b <= 126:  # Printable ASCII
                cur.append(b)
            else:
                if len(cur) >= min_len:
                    runs.append(cur.decode("utf-8", errors="ignore"))
                cur = bytearray()
        
        if len(cur) >= min_len:
            runs.append(cur.decode("utf-8", errors="ignore"))
        
        candidates = [
            r.strip() for r in runs
            if r.strip() and r.strip() not in MessageDecoder.BLACKLIST
        ]
        
        if not candidates:
            return ""
        
        return max(candidates, key=len)
    
    @staticmethod
    def decode_attributed_body(blob: bytes) -> str:
        """
        Decode attributedBody binary data from Messages database.
        
        Uses NSUnarchiver first, falls back to scanning for printable text.
        
        Args:
            blob: Binary attributedBody data
            
        Returns:
            Decoded message text, or empty string if decode fails
        """
        if not blob:
            return ""
        
        try:
            data = NSData.dataWithBytes_length_(blob, len(blob))
            obj = NSUnarchiver.unarchiveObjectWithData_(data)
            
            if hasattr(obj, "string"):
                s = str(obj.string()).strip()
                if s:
                    return s
            
            s = str(obj).strip()
            if s and s != "(null)":
                return s
        except Exception:
            pass
        
        return MessageDecoder._scan_printable(blob)
    
    @staticmethod
    def extract_text(row: sqlite3.Row) -> str:
        """
        Extract message text from a database row.
        
        Tries text column first, then decodes attributedBody if needed.
        
        Args:
            row: SQLite row from message table
            
        Returns:
            Message text string
        """
        txt = (row["text"] or "").strip()
        if txt:
            return txt
        
        blob = row["attributedBody"]
        if blob:
            return MessageDecoder.decode_attributed_body(blob)
        
        return ""


class AppleScriptEscaper:
    """Utilities for escaping strings for AppleScript."""
    
    @staticmethod
    def escape(text: str) -> str:
        """
        Escape a string for use in AppleScript.
        
        Args:
            text: String to escape
            
        Returns:
            Escaped string safe for AppleScript
        """
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')
        text = text.replace("\n", "\\n")
        return text


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

class MessagesDatabase:
    """Handles read-only operations on the Messages chat.db database."""
    
    def __init__(self, db_path: str = CHAT_DB):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to Messages chat.db file
        """
        self.db_path = db_path
    
    def _connect(self) -> sqlite3.Connection:
        """
        Create a read-only connection to the database.
        
        Returns:
            SQLite connection object
        """
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 2000;")
        return conn

    def fetch_chats(self, limit: int = 3000) -> List[sqlite3.Row]:
        """
        Fetch recent chats from the database.
        
        Args:
            limit: Maximum number of chats to fetch
            
        Returns:
            List of chat rows (chat_id, display_name, chat_identifier)
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT chat.ROWID as chat_id,
                       chat.display_name,
                       chat.chat_identifier
                FROM chat
                ORDER BY chat.ROWID DESC
                LIMIT ?
            """, (limit,))
            return cur.fetchall()
        finally:
            conn.close()
    
    def get_latest_message_id(self, chat_id: int) -> Optional[int]:
        """
        Get the ROWID of the most recent message in a chat.
        
        Args:
            chat_id: Chat ROWID
            
        Returns:
            Message ROWID, or None if no messages
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT MAX(message.ROWID) as max_id
                FROM message
                JOIN chat_message_join cmj ON cmj.message_id = message.ROWID
                WHERE cmj.chat_id = ?
            """, (chat_id,))
            row = cur.fetchone()
            return int(row["max_id"]) if row and row["max_id"] is not None else None
        finally:
            conn.close()
    
    def fetch_messages(self, chat_id: int, limit: int = 30) -> List[sqlite3.Row]:
        """
        Fetch recent messages from a chat.
        
        Args:
            chat_id: Chat ROWID
            limit: Maximum number of messages to fetch
            
        Returns:
            List of message rows (msg_id, text, attributedBody, is_from_me)
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    message.ROWID as msg_id,
                    message.text as text,
                    message.attributedBody as attributedBody,
                    message.is_from_me as is_from_me
                FROM message
                JOIN chat_message_join cmj ON cmj.message_id = message.ROWID
                WHERE cmj.chat_id = ?
                ORDER BY message.ROWID DESC
                LIMIT ?
            """, (chat_id, limit))
            return cur.fetchall()
        finally:
            conn.close()
    
    def get_chat_name(self, chat_id: int) -> str:
        """
        Get the name/identifier for a chat (used for sending messages).
        
        For group chats: returns display_name
        For 1:1 chats: returns chat_identifier (phone/email)
        
        Args:
            chat_id: Chat ROWID
            
        Returns:
            Chat name/identifier string
            
        Raises:
            RuntimeError: If chat_id not found
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT display_name, chat_identifier FROM chat WHERE ROWID=?",
                (chat_id,)
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"chat_id {chat_id} not found")
            
            display_name = (row["display_name"] or "").strip()
            identifier = (row["chat_identifier"] or "").strip()
            return display_name if display_name else identifier
        finally:
            conn.close()


# ============================================================================
# CONTACTS OPERATIONS
# ============================================================================

class ContactsManager:
    """Manages contact lookup using macOS Contacts framework."""
    
    def __init__(self):
        """Initialize contacts manager."""
        self.lookup: Dict[str, str] = {}
    
    def build_lookup(self) -> Dict[str, str]:
        """
        Build a lookup dictionary mapping normalized phone/email to contact names.
        
        Returns:
            Dictionary mapping normalized identifiers to contact names
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
        
        Args:
            display_name: Chat display name (often empty for 1:1 chats)
            chat_identifier: Chat identifier (phone/email for 1:1 chats)
            
        Returns:
            Formatted label string
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


# ============================================================================
# OPENAI OPERATIONS
# ============================================================================

class OpenAIClient:
    """Manages OpenAI API interactions."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = MODEL):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (if None, reads from OPENAI_API_KEY env)
            model: Model name to use
            
        Raises:
            RuntimeError: If API key is missing
        """
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "Missing OPENAI_API_KEY.\n"
                    "Set it then re-run:\n"
                    "  export OPENAI_API_KEY='sk-proj-...'\n"
                )
        
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.history: List[Dict[str, str]] = []
    
    def set_system_message(self, content: str) -> None:
        """
        Set the system message for the conversation.
        
        Args:
            content: System message content
        """
        if self.history and self.history[0].get("role") == "system":
            self.history[0] = {"role": "system", "content": content}
        else:
            self.history.insert(0, {"role": "system", "content": content})
    
    def trim_history(self, max_messages: int = MAX_CONTEXT_MESSAGES) -> None:
        """
        Trim conversation history to keep it within limits.
        
        Preserves system message, keeps only most recent messages.
        
        Args:
            max_messages: Maximum number of non-system messages to keep
        """
        system = self.history[:1] if self.history and self.history[0].get("role") == "system" else []
        rest = self.history[1:] if system else self.history
        
        if len(rest) > max_messages:
            rest = rest[-max_messages:]
        
        self.history = system + rest
    
    def chat(self, user_text: str) -> str:
        """
        Send a message to OpenAI and get a response.
        
        Implements retry logic with exponential backoff for rate limits.
        
        Args:
            user_text: User message text
            
        Returns:
            AI-generated response text
        """
        self.history.append({"role": "user", "content": user_text})
        self.trim_history()
        
        attempt = 0
        backoff = 0.75
        
        while True:
            attempt += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.history
                )
                
                reply = response.choices[0].message.content
                reply = (reply or "").strip() or "…"
                
                self.history.append({"role": "assistant", "content": reply})
                self.trim_history()
                
                return reply
            
            except openai.RateLimitError as e:
                msg = repr(e)
                if "insufficient_quota" in msg:
                    logger.error("OpenAI insufficient_quota: %s", msg)
                    return "OpenAI quota/billing issue — check API billing."
                
                logger.error("OpenAI rate-limited: %s", msg)
                if attempt >= 8:
                    return "I'm rate-limited — try again in a minute."
                
                sleep_s = min(20.0, backoff) * (0.8 + random.random() * 0.4)
                logger.info("Rate limited. Sleeping %.2fs...", sleep_s)
                time.sleep(sleep_s)
                backoff *= 2
            
            except openai.AuthenticationError as e:
                logger.error("OpenAI auth failed: %r", e)
                return "OpenAI auth failed. Check OPENAI_API_KEY."
            
            except Exception as e:
                logger.exception("OpenAI error: %r", e)
                return "Something went wrong calling OpenAI."


# ============================================================================
# MESSAGE SENDING
# ============================================================================

class MessageSender:
    """Handles sending messages via AppleScript."""
    
    @staticmethod
    def send_to_chat_by_name(chat_name: str, text: str) -> None:
        """
        Send a message to a chat by its name (group chats).
        
        Args:
            chat_name: Chat display name
            text: Message text to send
            
        Raises:
            RuntimeError: If AppleScript execution fails
        """
        safe_name = AppleScriptEscaper.escape(chat_name)
        safe_text = AppleScriptEscaper.escape(text)
        
        script = f'''
        tell application "Messages"
            set targetChat to first chat whose name is "{safe_name}"
            send "{safe_text}" to targetChat
        end tell
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip())
    
    @staticmethod
    def send_to_handle(handle: str, text: str) -> None:
        """
        Send a message to a handle (phone/email for 1:1 chats).
        
        Tries iMessage first, falls back to SMS.
        
        Args:
            handle: Phone number or email address
            text: Message text to send
            
        Raises:
            RuntimeError: If AppleScript execution fails
        """
        safe_handle = AppleScriptEscaper.escape(handle)
        safe_text = AppleScriptEscaper.escape(text)

        script = f'''
        tell application "Messages"
            set theText to "{safe_text}"

            -- try iMessage
            try
                set svc to first service whose service type = iMessage
                set b to buddy "{safe_handle}" of svc
                send theText to b
                return "sent_imessage"
            end try

            -- fallback to SMS (some Macs expose this as "SMS")
            try
                set svc2 to first service whose service type = SMS
                set b2 to buddy "{safe_handle}" of svc2
                send theText to b2
                return "sent_sms"
            end try

            error "No valid service/buddy for {safe_handle}"
        end tell
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip())


# ============================================================================
# CHAT PICKER
# ============================================================================

class ChatPicker:
    """Interactive chat selection interface."""
    
    def __init__(self, db: MessagesDatabase, contacts: ContactsManager):
        """
        Initialize chat picker.
        
        Args:
            db: MessagesDatabase instance
            contacts: ContactsManager instance
        """
        self.db = db
        self.contacts = contacts
    
    def pick(
        self,
        hint: Optional[str] = None,
        limit: int = LIST_LIMIT,
        use_contacts: bool = False
    ) -> Tuple[int, str]:
        """
        Interactive chat picker.
        
        Args:
            hint: Optional filter string for chat names
            limit: Maximum number of chats to display
            use_contacts: Whether to resolve contacts for display
            
        Returns:
            Tuple of (chat_id, chat_label)
            
        Raises:
            RuntimeError: If no chats match the hint
            SystemExit: If user chooses to quit
        """
        if use_contacts:
            self.contacts.build_lookup()
            if not CONTACTS_AVAILABLE:
                print("⚠️  Contacts framework not available. Install: pyobjc-framework-Contacts")

        rows = self.db.fetch_chats(limit=3000)

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
            
            if hint_l and not any(hint_l in s.lower() for s in [display_name, identifier, label]):
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


# ============================================================================
# MAIN BOT
# ============================================================================

class iMessageBot:
    """Main bot class that monitors and responds to messages."""
    
    def __init__(
        self,
        chat_id: int,
        chat_name: str,
        ai_client: OpenAIClient,
        db: MessagesDatabase
    ):
        """
        Initialize bot for a specific chat.
        
        Args:
            chat_id: Chat ROWID to monitor
            chat_name: Chat name/identifier for sending messages
            ai_client: OpenAIClient instance
            db: MessagesDatabase instance
        """
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
                self.last_seen_id
            )
        else:
            logger.info("No existing messages in chat")
    
    def should_respond(self, msg_id: int, text: str, from_me: int) -> bool:
        """
        Determine if bot should respond to a message.
        
        Note: This method assumes the message is already verified to be new
        (msg_id > last_seen_id). Message seen check is handled in run().
        
        Args:
            msg_id: Message ROWID
            text: Message text
            from_me: 1 if from bot user, 0 otherwise
            
        Returns:
            True if bot should respond
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
        """
        Extract user prompt from message text (remove trigger prefix).
        
        Args:
            text: Full message text
            
        Returns:
            User prompt without prefix
        """
        prefix_len = len(BOT_PREFIX)
        return text[prefix_len:].strip()
    
    def send_reply(self, reply: str) -> bool:
        """
        Send a reply message to the chat.
        
        Args:
            reply: Reply text to send
            
        Returns:
            True if sent successfully, False otherwise
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
        logger.info("Bot running for chat_id=%s send_name=%r", self.chat_id, self.chat_name)
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
                        ab_len = len(newest["attributedBody"]) if newest["attributedBody"] else 0
                        logger.info(
                            "DEBUG msg_id=%s from_me=%s text_len=%s attributedBody_len=%s text=%r",
                            msg_id, from_me, len(text), ab_len, text[:200]
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


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="iMessage GPT bot with Contacts name resolution"
    )
    parser.add_argument(
        "--hint",
        type=str,
        default=None,
        help="Filter chats by substring (name/identifier/contact)"
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="Skip picker and run for this chat_id"
    )
    parser.add_argument(
        "--with-contacts",
        action="store_true",
        help="Resolve 1:1 phone/email to Contacts.app names"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=LIST_LIMIT,
        help="How many recent chats to show"
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
            use_contacts=args.with_contacts
        )
    else:
        chosen_chat_id = args.chat_id
    
    # Get chat name for sending
    chat_send_name = db.get_chat_name(chosen_chat_id)
    
    # Create and run bot
    bot = iMessageBot(chosen_chat_id, chat_send_name, ai_client, db)
    bot.run()


if __name__ == "__main__":
    main()