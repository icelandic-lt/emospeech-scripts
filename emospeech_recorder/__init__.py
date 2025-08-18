"""Revoxx Recorder - A tool for recording emotional speech with real-time feedback."""

__version__ = "2.0.0"
__author__ = "Grammatek"

# Only import main entry point to avoid circular imports
__all__ = ["main", "EmoSpeechRecorder"]


def main():
    """Main entry point."""
    from .app import main as app_main

    app_main()


# Lazy import for Revoxx
def __getattr__(name):
    if name == "EmoSpeechRecorder":
        from .app import EmoSpeechRecorder

        return EmoSpeechRecorder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
