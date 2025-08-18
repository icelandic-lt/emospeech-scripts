"""Revoxx Recorder - A tool for recording emotional speech."""

__version__ = "1.0.0"
__author__ = "Grammatek"

# Only import main entry point to avoid circular imports
__all__ = ["main", "Revoxx"]


def main():
    """Main entry point."""
    from .app import main as app_main

    app_main()


# Lazy import for Revoxx
def __getattr__(name):
    if name == "Revoxx":
        from .app import Revoxx

        return Revoxx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
