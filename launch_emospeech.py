#!/usr/bin/env python3
"""Launcher script for EmoSpeech Recorder with proper app name on macOS."""

import os
import sys
import platform

def main():
    """Launch EmoSpeech Recorder with proper application name."""
    # Set the application name for macOS menu bar
    if platform.system() == 'Darwin':
        # This environment variable can help with some Python interpreters
        os.environ['PYTHON_APP_NAME'] = 'EmoSpeech Recorder'

        # Try to set process title
        try:
            import setproctitle
            setproctitle.setproctitle('EmoSpeech Recorder')
        except ImportError:
            # If setproctitle is not installed, try native method
            try:
                import ctypes
                libc = ctypes.CDLL('/usr/lib/libc.dylib')
                title = b'EmoSpeech Recorder\0'
                libc.setproctitle(ctypes.c_char_p(title))
            except Exception:
                pass

    # Import and run the main application
    from emospeech_recorder.app import main as app_main

    # Add default arguments if none provided
    if len(sys.argv) == 1:
        # No arguments provided, add defaults
        sys.argv.extend(['--audio-device', '1', '--script', 'scripts/t3_intensity_script.txt'])

    app_main()

if __name__ == '__main__':
    main()