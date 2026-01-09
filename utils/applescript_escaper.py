class AppleScriptEscaper:
    """Utilities for escaping strings for AppleScript."""

    @staticmethod
    def escape(text: str) -> str:
        """
        Escape a string for use in AppleScript.
        """
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')
        text = text.replace("\n", "\\n")
        return text

