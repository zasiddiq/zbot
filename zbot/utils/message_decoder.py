import sqlite3
from typing import Set

from Foundation import NSData, NSUnarchiver  # type: ignore


class MessageDecoder:
    """Utilities for decoding message text from Messages database."""

    # Blacklist of common strings found in attributedBody that aren't message text
    BLACKLIST: Set[str] = {
        "streamtyped",
        "NSAttributedString",
        "NSObject",
        "NSString",
        "__kIMMessagePartAttributeName",
    }

    @staticmethod
    def _scan_printable(blob: bytes, min_len: int = 4) -> str:
        """
        Scan binary data for printable ASCII sequences.
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
            r.strip()
            for r in runs
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
        """
        txt = (row["text"] or "").strip()
        if txt:
            return txt

        blob = row["attributedBody"]
        if blob:
            return MessageDecoder.decode_attributed_body(blob)

        return ""

