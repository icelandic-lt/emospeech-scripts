"""Main application for the EmoSpeech Recorder."""

import argparse
import sys
import platform
import time
import multiprocessing as mp
import queue
import threading
import tkinter as tk
from pathlib import Path
from typing import Optional

import sounddevice as sd

from .constants import KeyBindings, UIConstants
from .utils.config import RecorderConfig, load_config
from .utils.state import AppState
from .utils.file_manager import RecordingFileManager, ScriptFileManager
from .utils.settings_manager import SettingsManager
from .ui.main_window import MainWindow
from .audio.recorder import record_process
from .audio.player import playback_process, PlaybackController


class EmoSpeechRecorder:
    """Main application class for the EmoSpeech Recorder.

    This class manages the entire recording application, coordinating between
    the UI, audio recording/playback processes, and file management. It handles
    keyboard shortcuts, multiprocessing communication, and real-time spectrogram
    visualization.

    Attributes:
        config: Application configuration including audio, display, and UI settings
        script_file: Path to the Festival format script file containing utterances
        recording_dir: Directory where audio recordings are saved
        state: Application state manager tracking recording and UI state
        file_manager: Handles recording file operations and naming
        script_manager: Handles loading and parsing script files
        window: Main UI window instance
        audio_queue: Multiprocessing queue for real-time audio data
        record_queue: Queue for controlling the recording process
        playback_queue: Queue for controlling the playback process
        stop_signal: Shared value for interrupting playback
    """

    def __init__(self, config: RecorderConfig, script_file: Path, recording_dir: Path, debug: bool = False):
        """Initialize the application.

        Args:
            config: Application configuration object containing audio, display,
                and UI settings
            script_file: Path to script file in Festival data format
            recording_dir: Directory for saving recordings (created if not exists)
            debug: Enable debug output
        """
        self.config = config
        self.script_file = script_file
        self.recording_dir = recording_dir
        self.debug = debug

        # Initialize settings manager
        self.settings_manager = SettingsManager()

        # Apply saved settings to config
        self._apply_saved_settings()

        # Initialize state
        self.state = AppState()

        # Initialize file managers
        self.file_manager = RecordingFileManager(recording_dir)
        self.script_manager = ScriptFileManager()

        # Load script
        self._load_script()

        # Initialize multiprocessing components
        self._init_multiprocessing()

        # Start processes BEFORE UI initialization
        self._start_processes()

        # Initialize UI
        self._init_ui()

        # Bind keyboard shortcuts
        self._bind_keys()

        # Initial display update
        self._update_display()

        # Load initial spectrogram after UI is ready (like in rec_improved.py)
        if hasattr(self.window, 'mel_spectrogram'):
            self.root.after(UIConstants.INITIAL_DISPLAY_DELAY_MS, self._show_saved_recording)

    def _apply_saved_settings(self) -> None:
        """Apply saved settings to configuration."""
        settings = self.settings_manager.settings

        # Apply audio settings
        self.config.audio.sample_rate = settings.sample_rate
        self.config.audio.bit_depth = settings.bit_depth
        self.config.audio.__post_init__()  # Update dtype and subtype

        # Apply display settings
        self.config.display.show_spectrogram = settings.show_spectrogram
        self.config.ui.fullscreen = settings.fullscreen

        # Store window geometry for later use
        self._saved_window_geometry = settings.window_geometry

    def _load_script(self) -> None:
        """Load and parse the script file."""
        labels, utterances = self.script_manager.load_script(self.script_file)
        self.state.recording.labels = labels
        self.state.recording.utterances = utterances

        # Scan for existing recordings
        self.state.recording.takes = self.file_manager.scan_all_takes(labels)

    def _init_multiprocessing(self) -> None:
        """Initialize multiprocessing components."""
        # Create manager for shared state
        self.manager = mp.Manager()
        self.shared_state = self.manager.dict()

        # Audio queue for real-time processing
        self.audio_queue = mp.Queue(maxsize=100)

        # Control queues
        self.record_queue = mp.Queue()
        self.playback_queue = mp.Queue()

        # Stop signal for playback
        self.stop_signal = mp.Value('i', 0)

        # Initialize shared state
        self.shared_state['recording'] = False
        self.shared_state['playing'] = False
        self.shared_state['audio_queue_active'] = self.config.display.show_spectrogram
        self.shared_state['save_path'] = None

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        # For macOS: Set the process name before creating any windows
        if platform.system() == 'Darwin':
            try:
                # Try using PyObjC to set the application name
                from AppKit import NSApp, NSApplication
                NSApplication.sharedApplication()
                NSApp.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular

                # Set the application name
                from Foundation import NSProcessInfo
                NSProcessInfo.processInfo().setValue_forKey_('EmoSpeech Recorder', 'processName')
            except ImportError:
                # PyObjC not available, try ctypes approach
                try:
                    import ctypes
                    import ctypes.util

                    # Load the Foundation framework
                    foundation = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Foundation'))

                    # Get the current process info
                    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))

                    # Set process name using low-level approach
                    libc = ctypes.CDLL('/usr/lib/libc.dylib')
                    title = b'EmoSpeech Recorder\0'
                    libc.setproctitle(title)
                except Exception:
                    pass

        self.root = tk.Tk(className='EmoSpeech Recorder')
        self.root.title("EmoSpeech Recorder")

        # Create callbacks for menu actions
        app_callbacks = {
            'toggle_mel_spectrogram': self._toggle_mel_spectrogram,
            'update_audio_settings': self._update_audio_settings,
            'update_info_overlay': self._update_info_overlay
        }

        self.window = MainWindow(
            self.root,
            self.config,
            self.state.recording,
            self.state.ui,
            self.shared_state,
            app_callbacks,
            self.settings_manager
        )

        # Initialize playback controller
        self.playback_controller = PlaybackController(
            self.config.audio,
            self.recording_dir,
            self.playback_queue,
            self.shared_state,
            self.stop_signal
        )

        # Start audio queue processing (widget is always created now)
        if hasattr(self.window, 'mel_spectrogram') and self.window.mel_spectrogram is not None:
            self._start_audio_queue_processing()
            print("Mel spectrogram widget initialized and audio queue started")
        else:
            print("Warning: Mel spectrogram widget not found")
            print(f"Has mel_spectrogram attr: {hasattr(self.window, 'mel_spectrogram')}")
            if hasattr(self.window, 'mel_spectrogram'):
                print(f"mel_spectrogram value: {self.window.mel_spectrogram}")

    def _bind_keys(self) -> None:
        """Bind keyboard shortcuts."""
        self.root.bind(f'<{KeyBindings.RECORD}>', lambda e: self._toggle_recording())
        self.root.bind(f'<{KeyBindings.PLAY}>', lambda e: self._play_current())
        self.root.bind(f'<{KeyBindings.NAVIGATE_DOWN}>', lambda e: self._navigate(1))
        self.root.bind(f'<{KeyBindings.NAVIGATE_UP}>', lambda e: self._navigate(-1))
        self.root.bind(f'<{KeyBindings.BROWSE_TAKES_RIGHT}>', lambda e: self._browse_takes(1))
        self.root.bind(f'<{KeyBindings.BROWSE_TAKES_LEFT}>', lambda e: self._browse_takes(-1))
        # Toggle spectrogram can be 'm' or 'M'
        for key in KeyBindings.TOGGLE_SPECTROGRAM:
            self.root.bind(f'<{key}>', lambda e: self._toggle_mel_spectrogram())
        self.root.bind(f'<{KeyBindings.DELETE_RECORDING}>', lambda e: self._delete_current_recording())
        self.root.bind(f'<{KeyBindings.QUIT}>', lambda e: self._quit())
        self.root.bind(f'<{KeyBindings.TOGGLE_FULLSCREEN}>', lambda e: self.window.toggle_fullscreen())
        self.root.bind(f'<{KeyBindings.SHOW_HELP}>', lambda e: self.window._show_keyboard_shortcuts())
        self.root.bind(f'<{KeyBindings.SHOW_INFO}>', lambda e: self._show_info_overlay())

        # Window close event
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    def _start_processes(self) -> None:
        """Start background processes."""
        # Recording process
        self.record_process = mp.Process(
            target=record_process,
            args=(self.config.audio, self.audio_queue, self.shared_state, self.record_queue)
        )
        self.record_process.start()
        print(f"Recording process started: PID={self.record_process.pid}")

        # Playback process
        self.playback_process = mp.Process(
            target=playback_process,
            args=(self.config.audio, self.recording_dir, self.playback_queue,
                  self.shared_state, self.stop_signal)
        )
        self.playback_process.start()
        print(f"Playback process started: PID={self.playback_process.pid}")

    def _start_audio_queue_processing(self) -> None:
        """Start processing audio queue for real-time display."""
        self.shared_state['audio_queue_active'] = True

        # Start a transfer thread like in rec_improved.py
        def audio_transfer_thread():
            while self.shared_state.get('audio_queue_active', False):
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                    if hasattr(self.window, 'mel_spectrogram') and self.window.ui_state.spectrogram_visible:
                        # Use after() to update in main thread
                        self.root.after(0, lambda data=audio_data: self.window.mel_spectrogram.update_audio(data))
                except queue.Empty:
                    # Timeout is normal, just continue
                    pass
                except EOFError:
                    # Queue was closed, exit cleanly
                    print("Audio queue closed, exiting transfer thread")
                    break
                except Exception as e:
                    if "closed" not in str(e).lower():
                        print(f"Error in audio transfer thread: {e}")
                    break

        self.transfer_thread = threading.Thread(target=audio_transfer_thread)
        self.transfer_thread.daemon = True
        self.transfer_thread.start()


    def _toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.state.recording.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        """Start recording."""
        # Stop any playback
        self.playback_controller.stop_playback()

        # Update state
        self.state.recording.is_recording = True
        current_label = self.state.recording.current_label

        if not current_label:
            return

        # Increment take number
        take_num = self.state.recording.increment_take(current_label)

        # Set save path
        save_path = self.file_manager.get_recording_path(current_label, take_num)
        self.shared_state['save_path'] = str(save_path)

        # Clear and start spectrogram recording
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.clear()
            self.window.mel_spectrogram.start_recording()
            print(f"Spectrogram recording started, is_recording={self.window.mel_spectrogram.is_recording}")

        # Update info overlay if visible to show recording parameters
        if self.window.info_overlay.visible:
            recording_params = {
                'sample_rate': self.config.audio.sample_rate,
                'bit_depth': self.config.audio.bit_depth,
                'channels': self.config.audio.channels
            }
            self.window.info_overlay.show(is_recording=True, recording_params=recording_params)

        # Start recording
        self.record_queue.put('start')

        # Debug: check if audio transfer thread is running
        if hasattr(self, 'transfer_thread'):
            print(f"Audio transfer thread alive: {self.transfer_thread.is_alive()}")

        # Update display
        self._update_display()

    def _stop_recording(self) -> None:
        """Stop recording."""
        # Update state
        self.state.recording.is_recording = False

        # Stop recording
        self.record_queue.put('stop')

        # Stop spectrogram
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_recording()

        # Update displayed take
        current_label = self.state.recording.current_label
        if current_label:
            current_take = self.state.recording.get_take_count(current_label)
            self.state.recording.set_displayed_take(current_label, current_take)

            # Wait a bit for the file to be saved by the recording process
            # then load and display the recording
            self.root.after(UIConstants.POST_RECORDING_DELAY_MS, self._show_saved_recording)

        # Update display
        self._update_display()

        # Update info overlay if visible to show the new recording
        if self.window.info_overlay.visible:
            # Wait a bit for the file to be saved
            self.root.after(UIConstants.POST_RECORDING_DELAY_MS, self._update_info_overlay)

    def _play_current(self) -> None:
        """Play current recording."""
        if not self.state.is_ready_to_play():
            self.window.show_message("No recording available")
            return

        # Stop playback exactly like Left/Right keys do
        sd.stop()  # Immediate stop in main process
        self.playback_controller.stop_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        # Give the playback process time to handle the stop command
        time.sleep(UIConstants.PLAYBACK_STOP_DELAY)  # Small delay to ensure stop is processed

        current_label = self.state.recording.current_label
        current_take = self.state.recording.get_current_take(current_label)

        # Reset stop signal before playing
        self.stop_signal.value = 0

        if self.playback_controller.play_recording(current_label, current_take):
            # Start playback animation
            if hasattr(self.window, 'mel_spectrogram'):
                filepath = self.file_manager.get_recording_path(current_label, current_take)
                audio_data, sr = self.file_manager.load_audio(filepath)
                duration = len(audio_data) / sr
                self.window.mel_spectrogram.start_playback(duration)

    def _navigate(self, direction: int) -> None:
        """Navigate to next/previous utterance."""
        # Stop any current activity
        if self.state.recording.is_recording:
            self._stop_recording()

        self.playback_controller.stop_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        # Update index
        new_index = self.state.recording.current_index + direction
        if 0 <= new_index < len(self.state.recording.utterances):
            self.state.recording.current_index = new_index

            # Show saved recording if available
            self._show_saved_recording()

            # Update display
            self._update_display()

            # Update info overlay if visible
            if self.window.info_overlay.visible:
                self._update_info_overlay()

    def _browse_takes(self, direction: int) -> None:
        """Browse through different takes."""
        current_label = self.state.recording.current_label
        if not current_label:
            return

        # Stop playback and animation
        self.playback_controller.stop_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        # Get current take and all existing takes
        current_take = self.state.recording.get_current_take(current_label)
        existing_takes = self.file_manager.get_existing_takes(current_label)

        if not existing_takes:
            return

        # Find current position in the list
        try:
            current_index = existing_takes.index(current_take)
        except ValueError:
            # Current take not in list, find nearest
            current_index = 0
            for i, take in enumerate(existing_takes):
                if take > current_take:
                    current_index = max(0, i - 1)
                    break
                else:
                    current_index = i

        # Calculate new index
        new_index = current_index + direction

        # Check bounds and get new take
        if 0 <= new_index < len(existing_takes):
            new_take = existing_takes[new_index]
            self.state.recording.set_displayed_take(current_label, new_take)
            self._show_saved_recording()
            self._update_take_status()

            # Update info overlay if visible
            if self.window.info_overlay.visible:
                self._update_info_overlay()
        else:
            # No more takes in that direction
            direction_text = "forward" if direction > 0 else "backward"
            self.window.set_status(f"No more takes {direction_text}")

    def _update_take_status(self) -> None:
        """Update the take status display with relative position."""
        current_label = self.state.recording.current_label
        if not current_label:
            return

        current_take = self.state.recording.get_current_take(current_label)
        existing_takes = self.file_manager.get_existing_takes(current_label)

        if existing_takes and current_take in existing_takes:
            # Find position in the list
            position = existing_takes.index(current_take) + 1
            total = len(existing_takes)
            self.window.set_status(f"Take {position}/{total}")
        elif not existing_takes:
            self.window.set_status("No recordings")
        else:
            self.window.set_status("Ready")

    def _show_saved_recording(self) -> None:
        """Display saved recording in spectrogram."""
        if not hasattr(self.window, 'mel_spectrogram'):
            return

        current_label = self.state.recording.current_label
        if not current_label:
            return

        current_take = self.state.recording.get_current_take(current_label)

        if current_take == 0:
            # No recording exists - clear the spectrogram
            self.window.mel_spectrogram.clear()
            return

        filepath = self.file_manager.get_recording_path(current_label, current_take)

        if filepath.exists():
            try:
                audio_data, sr = self.file_manager.load_audio(filepath)
                self.window.mel_spectrogram.show_recording(audio_data, sr)
            except Exception as e:
                print(f"Error loading recording: {e}")
        else:
            # File doesn't exist - clear the spectrogram
            self.window.mel_spectrogram.clear()

    def _toggle_mel_spectrogram(self) -> None:
        """Toggle mel spectrogram visibility."""
        self.window.toggle_spectrogram()

        # Update audio queue state
        self.shared_state['audio_queue_active'] = self.state.ui.spectrogram_visible

        # Restart queue processing if needed
        if self.state.ui.spectrogram_visible:
            self._start_audio_queue_processing()
            # Show current recording if available
            self.root.after(50, self._show_saved_recording)

        # Save the preference
        self.settings_manager.update_setting('show_spectrogram', self.state.ui.spectrogram_visible)

        # Update menu checkbox if it exists
        if hasattr(self.window, 'mel_spectrogram_var'):
            self.window.mel_spectrogram_var.set(self.state.ui.spectrogram_visible)

    def _show_info_overlay(self) -> None:
        """Show audio info overlay with current recording information."""
        current_label = self.state.recording.current_label
        if not current_label:
            # No utterance selected
            self.window.show_info_overlay(is_recording=self.state.recording.is_recording)
            # Save the setting
            self.settings_manager.update_setting('show_info_overlay', self.window.info_overlay.visible)
            return

        if self.state.recording.is_recording:
            # Currently recording - show actual recording parameters
            recording_params = {
                'sample_rate': self.config.audio.sample_rate,
                'bit_depth': self.config.audio.bit_depth,
                'channels': self.config.audio.channels
            }
            self.window.show_info_overlay(is_recording=True, recording_params=recording_params)
        else:
            # Not recording - show info for current take (the one that would play with P)
            current_take = self.state.recording.get_current_take(current_label)

            if current_take > 0:
                # Get file path
                filepath = self.file_manager.get_recording_path(current_label, current_take)
                self.window.show_info_overlay(file_path=filepath, is_recording=False)
            else:
                # No recording for this utterance
                self.window.show_info_overlay(is_recording=False)

        # Save the setting after toggling
        self.settings_manager.update_setting('show_info_overlay', self.window.info_overlay.visible)

        # Update menu checkbox if it exists
        if hasattr(self.window, 'info_overlay_var'):
            self.window.info_overlay_var.set(self.window.info_overlay.visible)

    def _update_info_overlay(self) -> None:
        """Update the info overlay with current file information.

        This is called when navigating to update the overlay without toggling it.
        """
        current_label = self.state.recording.current_label
        if not current_label:
            return

        # Get current take that would play with P
        current_take = self.state.recording.get_current_take(current_label)

        if current_take > 0:
            # Get file path
            filepath = self.file_manager.get_recording_path(current_label, current_take)
            # Update overlay without toggling visibility
            self.window.info_overlay.show(file_path=filepath, is_recording=False)
        else:
            # No recording - update to show no recording
            self.window.info_overlay.show(is_recording=False)

    def _update_audio_settings(self) -> None:
        """Handle audio settings changes.

        Restarts audio processes with new settings.
        """
        # Stop current processes
        self.record_queue.put('quit')
        self.playback_queue.put('quit')

        # Wait for processes to finish
        self.record_process.join(timeout=1)
        self.playback_process.join(timeout=1)

        # Restart processes with new settings
        self._start_processes()

        # Restart audio queue processing if needed
        if self.config.display.show_spectrogram and hasattr(self.window, 'mel_spectrogram'):
            self._start_audio_queue_processing()

    def _delete_current_recording(self) -> None:
        """Delete the current recording take."""
        # Stop any playback first
        sd.stop()
        self.playback_controller.stop_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        current_label = self.state.recording.current_label
        if not current_label:
            self.window.set_status("No recording to delete")
            return

        current_take = self.state.recording.get_current_take(current_label)
        if current_take == 0:
            self.window.set_status("No recording to delete")
            return

        # Get the file path
        filepath = self.file_manager.get_recording_path(current_label, current_take)

        if not filepath.exists():
            self.window.set_status(f"Recording file not found: {filepath.name}")
            return

        try:
            # Delete the file
            filepath.unlink()

            # Update the takes count - find the highest existing take
            max_take = 0
            for take in range(1, current_take + 10):  # Check a reasonable range
                test_path = self.file_manager.get_recording_path(current_label, take)
                if test_path.exists() and take != current_take:
                    max_take = take

            # Update state with new max take
            self.state.recording.takes[current_label] = max_take

            # If we deleted the currently displayed take, find the next best one
            if current_take == self.state.recording.get_current_take(current_label):
                if max_take > 0:
                    # Find the highest available take to display
                    best_take = max_take
                    self.state.recording.set_displayed_take(current_label, best_take)
                else:
                    # No takes left
                    self.state.recording.set_displayed_take(current_label, 0)

            # Update display
            self._show_saved_recording()
            self._update_take_status()
            self.window.set_status(f"Deleted {filepath.name}")

        except Exception as e:
            self.window.set_status(f"Error deleting recording: {e}")

    def _update_display(self) -> None:
        """Update the main display."""
        self.window.update_display(
            self.state.recording.current_index,
            self.state.recording.is_recording
        )
        self._update_take_status()

    def _quit(self) -> None:
        """Clean shutdown of the application."""
        print("Shutting down...")

        # Save window geometry if not fullscreen
        if not self.root.attributes('-fullscreen'):
            self.settings_manager.update_setting('window_geometry', self.root.geometry())

        # Stop recording if active
        if self.state.recording.is_recording:
            self._stop_recording()

        # Stop audio queue processing
        self.shared_state['audio_queue_active'] = False

        # Wait for audio transfer thread to finish
        if hasattr(self, 'transfer_thread') and self.transfer_thread.is_alive():
            self.transfer_thread.join(timeout=0.5)

        # Stop processes
        self.record_queue.put('quit')
        self.playback_queue.put('quit')

        # Wait for processes to finish
        self.record_process.join(timeout=2)
        self.playback_process.join(timeout=2)

        # Terminate if still alive
        if self.record_process.is_alive():
            self.record_process.terminate()
        if self.playback_process.is_alive():
            self.playback_process.terminate()

        # Close UI
        self.root.quit()
        sys.exit(0)

    def run(self) -> None:
        """Run the application."""
        # Focus window on startup
        self.window.focus_window()

        # Start main loop
        self.root.mainloop()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments including:
            - script: Path to recording script file
            - recdir: Output directory for recordings
            - audio settings: devices, sample rate, channels, bit depth
            - display settings: spectrogram visibility
            - UI settings: window size, fullscreen, font size
    """
    # Create default config to get default values
    default_config = RecorderConfig()

    parser = argparse.ArgumentParser(
        description="Graphical interface for recording utterances from a script with real-time feedback",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Input/output files
    io = parser.add_argument_group('input/output files')
    io.add_argument(
        '--script',
        type=str,
        default='utts.data',
        help='recording script in Festival data format'
    )
    io.add_argument(
        '--recdir',
        type=str,
        default='recordings',
        help='output directory for recorded audio files'
    )

    # Audio configuration
    audio = parser.add_argument_group('audio configuration')
    audio.add_argument(
        '--show-devices',
        action='store_true',
        help='show available audio devices and exit'
    )
    audio.add_argument(
        '--audio-device',
        type=str,
        help='audio device name (sets both input and output)'
    )
    audio.add_argument(
        '--audio-in',
        type=str,
        default=None,
        help='input device index or name'
    )
    audio.add_argument(
        '--audio-out',
        type=str,
        default=None,
        help='output device index or name'
    )
    audio.add_argument(
        '--channels',
        type=int,
        default=default_config.audio.channels,
        help='n channels to record: 1 for mono, 2 for stereo'
    )
    audio.add_argument(
        '--sr',
        type=int,
        default=default_config.audio.sample_rate,
        help='sampling rate to record'
    )
    audio.add_argument(
        '--bits',
        type=int,
        choices=[16, 24],
        default=default_config.audio.bit_depth,
        help='bit depth, default=24, can be set to 16'
    )
    audio.add_argument(
        '--start-idx',
        type=int,
        default=0,
        help='starting index (not id) of UI'
    )

    # Display configuration group removed - settings are now persistent

    # UI configuration
    ui = parser.add_argument_group('UI configuration')
    ui.add_argument(
        '--fullscreen',
        action='store_true',
        help='start in fullscreen mode'
    )
    ui.add_argument(
        '--width',
        type=int,
        help='window width (pixels or percentage if <= 100)'
    )
    ui.add_argument(
        '--height',
        type=int,
        help='window height (pixels or percentage if <= 100)'
    )
    ui.add_argument(
        '--monitor',
        type=int,
        default=default_config.ui.monitor,
        help='monitor index for fullscreen'
    )
    ui.add_argument(
        '--font-size',
        type=int,
        default=default_config.ui.base_font_size,
        help='base font size'
    )

    # Configuration file
    parser.add_argument(
        '--config',
        type=Path,
        help='path to configuration file'
    )

    # Debug mode
    parser.add_argument(
        '--debug',
        action='store_true',
        help='enable debug output'
    )

    return parser.parse_args()


def show_audio_devices():
    """Show available audio devices and exit.

    Lists all available audio input and output devices with their
    capabilities, including channel counts, sample rates, and latencies.
    Useful for determining device indices to use with --audio-in/--audio-out.
    """
    print("\nAvailable audio devices:")
    print("=" * 50)
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        device_type = []
        if device['max_input_channels'] > 0:
            device_type.append("INPUT")
        if device['max_output_channels'] > 0:
            device_type.append("OUTPUT")
        print(f"{i}: {device['name']} [{', '.join(device_type)}]")
        print(f"   Channels: in={device['max_input_channels']}, out={device['max_output_channels']}")
        print(f"   Sample rates: {device['default_samplerate']}Hz")
        if device['default_low_input_latency'] > 0:
            print(f"   Input latency: {device['default_low_input_latency']*1000:.1f}ms")
        if device['default_low_output_latency'] > 0:
            print(f"   Output latency: {device['default_low_output_latency']*1000:.1f}ms")
        print()


def parse_audio_device(device_str: str) -> Optional[int]:
    """Parse audio device string to device index.

    Args:
        device_str: Device identifier - either a numeric index or
            partial device name (case-insensitive)

    Returns:
        Optional[int]: Device index if found, None otherwise

    Note:
        Device names are matched case-insensitively and partial
        matches are allowed (e.g., "scarlett" matches "Scarlett 2i2")
    """
    if device_str is None:
        return None

    # Try to parse as integer
    try:
        return int(device_str)
    except ValueError:
        pass

    # Search by name
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device_str.lower() in device['name'].lower():
            return i

    print(f"Warning: Device '{device_str}' not found")
    return None


def main() -> None:
    """Main entry point for the EmoSpeech Recorder application.

    Sets up multiprocessing for macOS compatibility, parses command line
    arguments, creates configuration, and launches the recorder application.
    Handles special modes like --show-devices for listing audio devices.
    """
    # Multiprocessing setup for macOS
    if platform.system() == 'Darwin':
        mp.set_start_method('spawn', force=True)

    # Parse arguments
    args = parse_arguments()

    # Show devices if requested
    if args.show_devices:
        show_audio_devices()
        sys.exit(0)

    # Create configuration
    config = RecorderConfig()

    # Load from config file if provided
    if args.config and args.config.exists():
        config = load_config(args.config)

    # Override with command line arguments
    # Audio settings
    config.audio.sample_rate = args.sr
    config.audio.channels = args.channels
    config.audio.bit_depth = args.bits
    # Trigger post_init to update dtype and subtype
    config.audio.__post_init__()

    # Handle audio devices
    if args.audio_device:
        device_idx = parse_audio_device(args.audio_device)
        if device_idx is not None:
            config.audio.input_device = device_idx
            config.audio.output_device = device_idx
    else:
        if args.audio_in:
            config.audio.input_device = parse_audio_device(args.audio_in)
        if args.audio_out:
            config.audio.output_device = parse_audio_device(args.audio_out)

    # Display settings are now loaded from saved settings

    # UI settings
    config.ui.fullscreen = args.fullscreen
    if args.width:
        config.ui.window_width = args.width
    if args.height:
        config.ui.window_height = args.height
    config.ui.monitor = args.monitor
    config.ui.base_font_size = args.font_size

    # Convert paths
    script_file = Path(args.script)
    recording_dir = Path(args.recdir)

    # Create and run application
    app = EmoSpeechRecorder(config, script_file, recording_dir, debug=args.debug)

    # Set starting index
    app.state.recording.current_index = args.start_idx

    # Run
    app.run()


if __name__ == '__main__':
    main()