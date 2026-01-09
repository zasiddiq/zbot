import sqlite3
from typing import List, Optional

from config import CHAT_DB


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
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT chat.ROWID as chat_id,
                       chat.display_name,
                       chat.chat_identifier
                FROM chat
                ORDER BY chat.ROWID DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def get_latest_message_id(self, chat_id: int) -> Optional[int]:
        """
        Get the ROWID of the most recent message in a chat.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(message.ROWID) as max_id
                FROM message
                JOIN chat_message_join cmj ON cmj.message_id = message.ROWID
                WHERE cmj.chat_id = ?
                """,
                (chat_id,),
            )
            row = cur.fetchone()
            return int(row["max_id"]) if row and row["max_id"] is not None else None
        finally:
            conn.close()

    def fetch_messages(self, chat_id: int, limit: int = 30) -> List[sqlite3.Row]:
        """
        Fetch recent messages from a chat.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
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
                """,
                (chat_id, limit),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def get_chat_name(self, chat_id: int) -> str:
        """
        Get the name/identifier for a chat (used for sending messages).
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT display_name, chat_identifier FROM chat WHERE ROWID=?",
                (chat_id,),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"chat_id {chat_id} not found")

            display_name = (row["display_name"] or "").strip()
            identifier = (row["chat_identifier"] or "").strip()
            return display_name if display_name else identifier
        finally:
            conn.close()

