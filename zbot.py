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

from zbot.cli import main


if __name__ == "__main__":
    main()