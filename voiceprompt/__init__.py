"""VoicePrompt local push-to-talk dictation app."""

from voiceprompt.dpi import enable_dpi_awareness

enable_dpi_awareness()

__all__ = ["__version__"]

__version__ = "0.5.1"
