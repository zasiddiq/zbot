import subprocess

from utils.applescript_escaper import AppleScriptEscaper


class MessageSender:
    """Handles sending messages via AppleScript."""

    @staticmethod
    def send_to_chat_by_name(chat_name: str, text: str) -> None:
        """
        Send a message to a chat by its name (group chats).
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
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip())

    @staticmethod
    def send_to_handle(handle: str, text: str) -> None:
        """
        Send a message to a handle (phone/email for 1:1 chats).
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
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip())

