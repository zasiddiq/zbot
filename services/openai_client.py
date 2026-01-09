import os
import random
import time
from typing import Dict, List, Optional

import openai
from openai import OpenAI

from config import MAX_CONTEXT_MESSAGES, MODEL, logger


class OpenAIClient:
    """Manages OpenAI API interactions."""

    def __init__(self, api_key: Optional[str] = None, model: str = MODEL):
        """
        Initialize OpenAI client.
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
        """Set the system message for the conversation."""
        if self.history and self.history[0].get("role") == "system":
            self.history[0] = {"role": "system", "content": content}
        else:
            self.history.insert(0, {"role": "system", "content": content})

    def trim_history(self, max_messages: int = MAX_CONTEXT_MESSAGES) -> None:
        """
        Trim conversation history to keep it within limits.
        """
        system = (
            self.history[:1]
            if self.history and self.history[0].get("role") == "system"
            else []
        )
        rest = self.history[1:] if system else self.history

        if len(rest) > max_messages:
            rest = rest[-max_messages:]

        self.history = system + rest

    def chat(self, user_text: str) -> str:
        """
        Send a message to OpenAI and get a response.
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
                    messages=self.history,
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

