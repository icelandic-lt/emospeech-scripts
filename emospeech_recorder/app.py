"""Main application for Revoxx."""

# Set matplotlib backend before any matplotlib imports
import matplotlib
matplotlib.use('TkAgg')

import argparse
import sys
import platform
import time
import os
import multiprocessing as mp
import queue
import threading
import tkinter as tk
from pathlib import Path
import signal
from typing import Optional
import traceback

import sounddevice as sd

from .constants import KeyBindings, UIConstants, FileConstants
from .utils.config import RecorderConfig, load_config
from .utils.state import AppState
from .utils.file_manager import RecordingFileManager, ScriptFileManager
from .utils.settings_manager import SettingsManager
from .ui.main_window import MainWindow
from .utils.audio_devices import (
    list_input_devices,
    list_output_devices,
    get_device_name_by_index,
    get_default_device_indices,
    refresh_devices_backend,
)
from .audio.recorder import record_process
from .audio.player import playback_process
from .audio.audio_buffer import AudioBuffer
from .audio.buffer_manager import BufferManager
from .audio.shared_state import SharedState


class Revoxx:
    """Main application class for Revoxx.

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

        # Track default-device notifications
        self._default_input_in_effect = False
        self._default_output_in_effect = False
        self._notified_default_input = False
        self._notified_default_output = False
        self.last_output_error = False

        # Initialize settings manager
        self.settings_manager = SettingsManager()

        # Apply saved settings to config
        self._apply_saved_settings()

        # Initialize state
        self.state = AppState()

        # Monitoring state
        self.is_monitoring = False
        self.saved_spectrogram_state = None
        self.saved_level_meter_state = None

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
        # Expose quit callback to UI menu if needed
        if hasattr(self, 'window') and hasattr(self.window, 'app_callbacks'):
            try:
                self.window.app_callbacks['quit'] = self._quit
            except Exception:
                pass

        # Bind keyboard shortcuts
        self._bind_keys()

        # Initial display update
        self._update_display()

        # Load initial spectrogram after UI is ready
        if hasattr(self.window, 'mel_spectrogram'):
            self.root.after(UIConstants.INITIAL_DISPLAY_DELAY_MS, self._show_saved_recording)

    def _apply_saved_settings(self) -> None:
        """Apply saved settings to configuration."""
        settings = self.settings_manager.settings

        # Audio settings
        self.config.audio.sample_rate = settings.sample_rate
        self.config.audio.bit_depth = settings.bit_depth
        self.config.audio.sync_response_time_ms = settings.audio_sync_response_time_ms
        self.config.audio.__post_init__()  # Update dtype and subtype

        # Restore preferred devices by name if possible, but only if not set via CLI
        try:
            # Input device
            if self.config.audio.input_device is None:
                restored = False
                if settings.input_device is not None:
                    name = settings.input_device
                    for dev in list_input_devices():
                        if dev['name'] == name:
                            self.config.audio.input_device = dev['index']
                            restored = True
                            break
                # If not restored, we will use system default
                self._default_input_in_effect = not restored
            else:
                self._default_input_in_effect = False

            # Output device
            if self.config.audio.output_device is None:
                restored = False
                if settings.output_device is not None:
                    name = settings.output_device
                    for dev in list_output_devices():
                        if dev['name'] == name:
                            self.config.audio.output_device = dev['index']
                            restored = True
                            break
                self._default_output_in_effect = not restored
            else:
                self._default_output_in_effect = False
        except Exception:
            # On any error, fall back silently, treat as default in effect
            if self.config.audio.input_device is None:
                self._default_input_in_effect = True
            if self.config.audio.output_device is None:
                self._default_output_in_effect = True

        # Display settings
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
        self.manager_dict = self.manager.dict()
        # Shutdown event to coordinate clean exit across processes/threads
        self.shutdown_event = mp.Event()

        # Create buffer manager for shared memory lifecycle
        self.buffer_manager = BufferManager(max_buffers=5)

        # Create struct-based shared state
        self.shared_state = SharedState(create=True)

        # Initialize audio settings in struct shared state
        # Determine format type based on file extension constant
        format_type = 1 if FileConstants.AUDIO_FILE_EXTENSION == '.flac' else 0
        self.shared_state.update_audio_settings(
            sample_rate=self.config.audio.sample_rate,
            bit_depth=self.config.audio.bit_depth,
            channels=self.config.audio.channels,
            format_type=format_type
        )

        # Initialize recording state to STOPPED
        self.shared_state.stop_recording()

        # Initialize playback state to IDLE
        self.shared_state.stop_playback()

        # Audio queue for real-time processing
        self.audio_queue = mp.Queue(maxsize=100)

        # Control queues
        self.record_queue = mp.Queue()
        self.playback_queue = mp.Queue()

        # Initialize shared state
        self.manager_dict['recording'] = False
        self.manager_dict['playing'] = False
        self.manager_dict['audio_queue_active'] = self.config.display.show_spectrogram
        self.manager_dict['save_path'] = None
        self.manager_dict['debug'] = self.debug

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
                NSProcessInfo.processInfo().setValue_forKey_('Revoxx', 'processName')
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
                    title = b'Revoxx\0'
                    libc.setproctitle(title)
                except Exception:
                    pass

        self.root = tk.Tk(className='Revoxx')
        self.root.title("Revoxx")

        # macOS: Route the standard application "Quit" (CMD+Q) to our central _quit()
        if platform.system() == 'Darwin':
            try:
                # Override the Cocoa default quit command used by Tk
                self.root.createcommand('tk::mac::Quit', self._quit)
            except Exception:
                pass

        # Create callbacks for menu actions
        app_callbacks = {
            'toggle_mel_spectrogram': self._toggle_mel_spectrogram,
            'toggle_level_meter': self._toggle_level_meter,
            'toggle_monitoring': self._toggle_monitoring,
            'update_audio_settings': self._update_audio_settings,
            'update_info_overlay': self._update_info_overlay,
            'set_input_device': self._set_input_device,
            'set_output_device': self._set_output_device,
            'set_input_channel_mapping': self._set_input_channel_mapping,
            'set_output_channel_mapping': self._set_output_channel_mapping,
            'quit': self._quit
        }

        self.window = MainWindow(
            self.root,
            self.config,
            self.state.recording,
            self.state.ui,
            self.manager_dict,
            app_callbacks,
            self.settings_manager,
            self.shared_state  # Pass struct shared state
        )

        # Start audio queue processing (widget is always created now)
        if hasattr(self.window, 'mel_spectrogram') and self.window.mel_spectrogram is not None:
            # Delay a bit to ensure Manager server is fully up before background thread accesses it
            self.root.after(50, self._start_audio_queue_processing)

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
        # Toggle level meter can be 'l' or 'L'
        for key in KeyBindings.TOGGLE_LEVEL_METER:
            self.root.bind(f'<{key}>', lambda e: self._toggle_level_meter())
        self.root.bind(f'<{KeyBindings.TOGGLE_MONITORING}>', lambda e: self._toggle_monitoring())
        self.root.bind(f'<{KeyBindings.DELETE_RECORDING}>', lambda e: self._delete_current_recording())
        self.root.bind(f'<{KeyBindings.QUIT}>', lambda e: self._quit())
        self.root.bind(f'<{KeyBindings.TOGGLE_FULLSCREEN}>', lambda e: self.window.toggle_fullscreen())
        self.root.bind(f'<{KeyBindings.SHOW_HELP}>', lambda e: self.window._show_keyboard_shortcuts())
        self.root.bind(f'<{KeyBindings.SHOW_INFO}>', lambda e: self._show_info_overlay())

        # Window close event
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        # macOS Command+Q should quit like 'q'
        try:
            self.root.bind_all('<Command-q>', lambda e: self._quit())
            self.root.bind_all('<Command-Q>', lambda e: self._quit())
        except Exception:
            pass

    def _start_processes(self) -> None:
        """Start background processes."""
        # Recording process with hardware synchronization
        self.record_process = mp.Process(
            target=record_process,
            args=(self.config.audio, self.audio_queue, self.shared_state.name,
                  self.record_queue, self.manager_dict, self.shutdown_event)
        )
        self.record_process.start()

        # Playback process with hw synchronization
        self.playback_process = mp.Process(
            target=playback_process,
            args=(self.config.audio, self.playback_queue, self.shared_state.name, self.shutdown_event)
        )
        self.playback_process.start()


    def _start_audio_queue_processing(self) -> None:
        """Start processing audio queue for real-time display."""
        self.manager_dict['audio_queue_active'] = True

        # Start a transfer thread
        def audio_transfer_thread():
            try:
                while True:
                    # Check active flag with guard; manager may already be gone
                    try:
                        active = self.manager_dict.get('audio_queue_active', False)
                    except Exception:
                        break
                    if not active:
                        break

                    try:
                        audio_data = self.audio_queue.get(timeout=0.1)

                        # Update mel spectrogram if visible
                        if hasattr(self.window, 'mel_spectrogram') and self.window.ui_state.spectrogram_visible:
                            # Use after() to update in main thread
                            self.root.after(0, lambda data=audio_data: self.window.mel_spectrogram.update_audio(data))

                    except queue.Empty:
                        # Timeout is normal, just continue
                        pass
                    except EOFError:
                        # Queue was closed, exit cleanly
                        break
                    except Exception as e:
                        if "closed" not in str(e).lower():
                            print(f"Error in audio transfer thread: {e}")
                        break
            except (BrokenPipeError, OSError, EOFError):
                # IPC endpoints closed during shutdown; exit quietly
                pass

        self.transfer_thread = threading.Thread(target=audio_transfer_thread)
        self.transfer_thread.daemon = True
        self.transfer_thread.start()


    def _toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.state.recording.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_audio_capture(self, mode: str) -> None:
        """Start audio capture in recording or monitoring mode.

        Args:
            mode: Must be either 'recording' or 'monitoring'
        """
        if mode not in ('recording', 'monitoring'):
            raise ValueError(f"Invalid mode: {mode}. Must be 'recording' or 'monitoring'")

        is_recording = (mode == 'recording')

        # Stop any active monitoring or playback
        if self.is_monitoring:
            self._stop_monitoring_mode()
        if is_recording:
            self._stop_synchronized_playback()

        # Recording-specific setup
        if is_recording:
            # Update state
            self.state.recording.is_recording = True
            current_label = self.state.recording.current_label

            if not current_label:
                return

            # Increment take number and set save path
            take_num = self.state.recording.increment_take(current_label)
            save_path = self.file_manager.get_recording_path(current_label, take_num)
            self.manager_dict['save_path'] = str(save_path)
        else:
            # Monitoring-specific setup
            self.is_monitoring = True
            # Save current UI state
            self.saved_spectrogram_state = self.state.ui.spectrogram_visible
            self.saved_level_meter_state = self.window.level_meter_var.get() if hasattr(self.window, 'level_meter_var') else False

            # Show both visualizations
            if not self.state.ui.spectrogram_visible:
                self._toggle_mel_spectrogram()
            if hasattr(self.window, 'level_meter_var') and not self.window.level_meter_var.get():
                self.window._toggle_level_meter_callback()
                self.settings_manager.update_setting('show_level_meter', True)
                self.root.update_idletasks()

            # Reset level meter when entering monitoring mode
            if hasattr(self.window, 'embedded_level_meter') and self.window.embedded_level_meter:
                try:
                    self.window.embedded_level_meter.reset()
                except Exception:
                    pass

        # Clear and start spectrogram
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.clear()
            self.window.mel_spectrogram.start_recording(self.config.audio.sample_rate)

        # Update info overlay
        if self.window.info_overlay.visible:
            recording_params = {
                'sample_rate': self.config.audio.sample_rate,
                'bit_depth': self.config.audio.bit_depth,
                'channels': self.config.audio.channels
            }
            self.window.info_overlay.show(
                recording_params,
                is_recording=True,
                is_monitoring=(mode == 'monitoring')
            )

        # If default input device is in effect and not yet notified, inform user once
        if self._default_input_in_effect and not self._notified_default_input:
            try:
                self.window.show_message("Using system default input device (no saved/available selection)")
            except Exception:
                pass
            self._notified_default_input = True

        # Preflight: quick rescan and availability check
        try:
            refresh_devices_backend()
        except Exception:
            pass

        # Verify selected input device still exists (if set)
        if self.config.audio.input_device is not None:
            available = [d['index'] for d in list_input_devices()]
            if self.config.audio.input_device not in available:
                # Device missing → message and fallback to default for this run
                self.window.set_status("Selected input device not found. Using system default.")
                # Do not change persisted selection; just let record process try with None
                self.record_queue.put({'action': 'set_input_device', 'index': None})

        # Start audio capture
        self.record_queue.put({'action': 'start'})

        # Update UI
        if is_recording:
            self._update_display()
        else:
            self.window.set_status("Monitoring input levels...")
            if hasattr(self.window, 'monitoring_var'):
                self.window.monitoring_var.set(True)

    def _start_recording(self) -> None:
        """Start recording."""
        self._start_audio_capture('recording')

    def _stop_audio_capture(self, mode: str) -> None:
        """Stop audio capture in recording or monitoring mode.

        Args:
            mode: Must be either 'recording' or 'monitoring'
        """
        if mode not in ('recording', 'monitoring'):
            raise ValueError(f"Invalid mode: {mode}. Must be 'recording' or 'monitoring'")

        is_recording = (mode == 'recording')

        # Stop audio capture & spectrogram
        self.record_queue.put({'action': 'stop'})
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_recording()

        # Recording-specific cleanup
        if is_recording:
            # Update state
            self.state.recording.is_recording = False

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
        else:
            # Monitoring-specific cleanup
            self.is_monitoring = False

            # Restore UI state
            if self.saved_spectrogram_state is not None and self.saved_spectrogram_state != self.state.ui.spectrogram_visible:
                self._toggle_mel_spectrogram()

            if hasattr(self.window, 'level_meter_var') and self.saved_level_meter_state is not None:
                current_state = self.window.level_meter_var.get()
                if self.saved_level_meter_state != current_state:
                    self.window._toggle_level_meter_callback()

            # Clear saved states
            self.saved_spectrogram_state = None
            self.saved_level_meter_state = None

            # Update UI
            self.window.set_status("Ready")
            if hasattr(self.window, 'monitoring_var'):
                self.window.monitoring_var.set(False)

            # Show previous recording if one exists
            self._show_saved_recording()

            # Update info overlay if visible to show the current recording
            if self.window.info_overlay.visible:
                self._update_info_overlay()

    def _stop_recording(self) -> None:
        """Stop recording."""
        self._stop_audio_capture('recording')

    def _play_current(self) -> None:
        """Play current recording."""
        if not self.state.is_ready_to_play():
            self.window.show_message("No recording available")
            return

        # Stop monitoring if active
        if self.is_monitoring:
            self._stop_monitoring_mode()

        # Stop playback exactly like Left/Right keys do
        sd.stop()  # Immediate stop in main process
        self._stop_synchronized_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        # Reset meter via shared state before starting a new playback
        try:
            self.shared_state.reset_level_meter()
        except Exception:
            pass

        # Give the playback process time to handle the stop command
        time.sleep(UIConstants.PLAYBACK_STOP_DELAY)  # Small delay to ensure stop is processed
        # Also clear playback status to IDLE
        try:
            self.shared_state.stop_playback()
        except Exception:
            pass

        current_label = self.state.recording.current_label
        current_take = self.state.recording.get_current_take(current_label)

        # If default output device is in effect and not yet notified, inform user once
        if self._default_output_in_effect and not self._notified_default_output:
            try:
                self.window.show_message("Using system default output device (no saved/available selection)")
            except Exception:
                pass
            self._notified_default_output = True

        # Additionally, warn once if last stream open failed or device likely unavailable
        if hasattr(self, 'last_output_error') and self.last_output_error:
            self.window.set_status("Output device unavailable. Using system default if possible.")
            self.last_output_error = False

        # Quick rescan before playback
        try:
            refresh_devices_backend()
        except Exception:
            pass

        # Verify selected output device still exists (if set)
        if self.config.audio.output_device is not None:
            available = [d['index'] for d in list_output_devices()]
            if self.config.audio.output_device not in available:
                self.window.set_status("Selected output device not found. Using system default.")
                try:
                    self.playback_queue.put({'action': 'set_output_device', 'index': None}, block=False)
                except Exception:
                    pass

        # Hardware synchronized playback
        filepath = self.file_manager.get_recording_path(current_label, current_take)
        if filepath.exists():
            # Load audio
            audio_data, sr = self.file_manager.load_audio(filepath)
            duration = len(audio_data) / sr

            # Reset meter when starting playback of a file
            if hasattr(self.window, 'embedded_level_meter') and self.window.embedded_level_meter:
                try:
                    self.window.embedded_level_meter.reset()
                except Exception:
                    pass

            # Create shared audio buffer using buffer manager
            audio_buffer = self.buffer_manager.create_buffer(audio_data)

            # Send play command with buffer metadata
            self.playback_queue.put({
                'action': 'play',
                'buffer_metadata': audio_buffer.get_metadata(),
                'sample_rate': sr
            })

            # Close our reference but don't unlink - buffer manager handles lifecycle
            audio_buffer.close()

            # Start animations
            if hasattr(self.window, 'mel_spectrogram'):
                self.window.mel_spectrogram.start_playback(duration, sr)

            # Update level meter for playback if visible
            level_meter_visible = self.window.level_meter_var.get() if hasattr(self.window, 'level_meter_var') else False
            if level_meter_visible:
                # Schedule periodic updates during playback
                self._start_playback_level_monitoring(filepath)

    def _navigate(self, direction: int) -> None:
        """Navigate to next/previous utterance."""
        # Stop any current activity
        if self.state.recording.is_recording:
            self._stop_recording()

        self._stop_synchronized_playback()
        if hasattr(self.window, 'mel_spectrogram'):
            self.window.mel_spectrogram.stop_playback()

        # Reset level meter via shared state to ensure producer/consumer sync
        try:
            self.shared_state.reset_level_meter()
        except Exception:
            pass

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
        self._stop_synchronized_playback()
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
            # Reset level meter via shared state when switching takes
            try:
                self.shared_state.reset_level_meter()
            except Exception:
                pass
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
            # No recording exists - clear the spectrogram and reset meter
            self.window.mel_spectrogram.clear()
            if hasattr(self.window, 'embedded_level_meter') and self.window.embedded_level_meter:
                try:
                    self.window.embedded_level_meter.reset()
                except Exception:
                    pass
            return

        filepath = self.file_manager.get_recording_path(current_label, current_take)

        if filepath.exists():
            try:
                audio_data, sr = self.file_manager.load_audio(filepath)
                # Reset meter via shared state when switching to a new file
                try:
                    self.shared_state.reset_level_meter()
                except Exception:
                    pass
                self.window.mel_spectrogram.show_recording(audio_data, sr)
            except Exception as e:

                print(f"Error loading recording: {e}")
                traceback.print_exc()
        else:
            # File doesn't exist - clear the spectrogram
            self.window.mel_spectrogram.clear()

    def _toggle_mel_spectrogram(self) -> None:
        """Toggle mel spectrogram visibility."""
        self.window.toggle_spectrogram()

        # Update audio queue state - needed if either spectrogram or level meter is visible
        self._update_audio_queue_state()

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

    def _toggle_level_meter(self) -> None:
        """Toggle level meter visibility."""
        # Toggle the embedded level meter in the main window
        if hasattr(self.window, 'level_meter_var'):
            # Toggle the checkbox, which will trigger the callback
            current_state = self.window.level_meter_var.get()
            self.window.level_meter_var.set(not current_state)
            self.window._toggle_level_meter_callback()

            # Update audio queue state - needed if either spectrogram or level meter is visible
            self._update_audio_queue_state()
            # Start audio queue processing if needed and not already running
            show_meter = self.window.level_meter_var.get()
            if show_meter and not self.manager_dict.get('audio_queue_active', False):
                self._start_audio_queue_processing()

    def _toggle_monitoring(self) -> None:
        """Toggle monitoring mode - shows both level meter and mel spectrogram."""
        if self.is_monitoring:
            self._stop_monitoring_mode()
        else:
            self._start_monitoring_mode()


    def _start_monitoring_mode(self) -> None:
        """Start monitoring mode using record process without saving."""
        self._start_audio_capture('monitoring')

    def _stop_monitoring_mode(self) -> None:
        """Stop monitoring mode - restore UI state."""
        self._stop_audio_capture('monitoring')

    def _update_audio_queue_state(self) -> None:
        """Update audio queue state based on whether any visualizations need audio."""
        # Audio queue is needed if either spectrogram or level meter is visible
        level_meter_visible = self.window.level_meter_var.get() if hasattr(self.window, 'level_meter_var') else False
        needs_audio = self.state.ui.spectrogram_visible or level_meter_visible

        self.manager_dict['audio_queue_active'] = needs_audio

    def _show_info_overlay(self) -> None:
        """Show audio info overlay with current recording information."""
        current_label = self.state.recording.current_label
        if not current_label:
            # No utterance selected - show current settings
            recording_params = {
                'sample_rate': self.config.audio.sample_rate,
                'bit_depth': self.config.audio.bit_depth,
                'channels': self.config.audio.channels
            }
            self.window.show_info_overlay(recording_params, self.state.recording.is_recording)
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
            self.window.show_info_overlay(recording_params, True)
        else:
            # Not recording - start with default settings
            recording_params = {
                'sample_rate': self.config.audio.sample_rate,
                'bit_depth': self.config.audio.bit_depth,
                'channels': self.config.audio.channels
            }

            # Try to get actual file info if a recording exists
            current_take = self.state.recording.get_current_take(current_label)
            if current_take > 0:
                filepath = self.file_manager.get_recording_path(current_label, current_take)
                if filepath.exists():
                    file_info = self.file_manager.get_file_info(filepath)
                    if file_info:
                        sample_rate, bit_depth, format_name, channels, duration = file_info
                        # Override with actual file parameters
                        recording_params = {
                            'sample_rate': sample_rate,
                            'bit_depth': bit_depth,
                            'format': format_name,
                            'channels': channels,
                            'duration': duration,
                            'size': filepath.stat().st_size
                        }

            self.window.show_info_overlay(recording_params, False)

        # Save the setting after toggling
        self.settings_manager.update_setting('show_info_overlay', self.window.info_overlay.visible)

        # Update menu checkbox if it exists
        if hasattr(self.window, 'info_overlay_var'):
            self.window.info_overlay_var.set(self.window.info_overlay.visible)

    def _update_info_overlay(self) -> None:
        """Update the info overlay with current file information.

        This is called when navigating to update the overlay without toggling it.
        """
        # Check if window is initialized
        if not hasattr(self, 'window') or self.window is None:
            return

        current_label = self.state.recording.current_label
        if not current_label:
            return

        recording_params = {
            'sample_rate': self.config.audio.sample_rate,
            'bit_depth': self.config.audio.bit_depth,
            'channels': self.config.audio.channels
        }


        current_take = self.state.recording.get_current_take(current_label)
        if current_take > 0:
            # Get recording parameters for file
            filepath = self.file_manager.get_recording_path(current_label, current_take)
            if filepath.exists():
                file_info = self.file_manager.get_file_info(filepath)
                if file_info:
                    sample_rate, bit_depth, format_name, channels, duration = file_info
                    recording_params = {
                        'sample_rate': sample_rate,
                        'bit_depth': bit_depth,
                        'format': format_name,
                        'channels': channels,
                        'duration': duration,
                        'size': filepath.stat().st_size
                    }

        self.window.info_overlay.show(recording_params, is_recording=False)

    def _update_audio_settings(self) -> None:
        """Handle audio settings changes.

        Updates struct shared state with new settings instead of restarting processes.
        """
        # Note: self.config.audio should already be updated by the settings dialog
        # before this method is called

        # Update struct shared state with new audio settings
        # Determine format type based on file extension constant
        format_type = 1 if FileConstants.AUDIO_FILE_EXTENSION == '.flac' else 0

        # Update settings in shared memory
        self.shared_state.update_audio_settings(
            sample_rate=self.config.audio.sample_rate,
            bit_depth=self.config.audio.bit_depth,
            channels=self.config.audio.channels,
            format_type=format_type
        )

    def _set_input_device(self, index: int) -> None:
        """Set preferred input device by index and persist by name.

        Effect will apply to next (re)start of input streams.
        """
        try:
            self.config.audio.input_device = index
            name = get_device_name_by_index(index)
            if name:
                self.settings_manager.update_setting('input_device', name)
            self.window.set_status(f"Input device set to #{index}: {name or 'Unknown'}")
            # Since a specific device was chosen, default is no longer in effect
            self._default_input_in_effect = False
            self._notified_default_input = False
            # Propagate to recorder process for future recordings
            try:
                self.record_queue.put({'action': 'set_input_device', 'index': index}, block=False)
            except Exception:
                pass
        except Exception as e:
            self.window.set_status(f"Failed to set input device: {e}")

    def _set_input_channel_mapping(self, mapping: Optional[list]) -> None:
        """Set custom input channel mapping (None means device default)."""
        try:
            # Persist
            self.settings_manager.update_setting('input_channel_mapping', mapping)
            # No immediate restart; applies on next recording/monitoring start
            label = "Device default" if mapping is None else f"Input channels: {[m+1 for m in mapping]}"
            self.window.set_status(label)
        except Exception as e:
            self.window.set_status(f"Failed to set input channels: {e}")
        # Propagate mapping to record process
        try:
            self.record_queue.put({'action': 'set_input_channel_mapping', 'mapping': mapping}, block=False)
        except Exception:
            pass

    def _set_output_device(self, index: int) -> None:
        """Set preferred output device by index and persist by name.

        Effect will apply to next (re)start of output streams.
        """
        try:
            self.config.audio.output_device = index
            name = get_device_name_by_index(index)
            if name:
                self.settings_manager.update_setting('output_device', name)
            self.window.set_status(f"Output device set to #{index}: {name or 'Unknown'}")
            self._default_output_in_effect = False
            self._notified_default_output = False
            # Propagate to playback process for future playback
            try:
                self.playback_queue.put({'action': 'set_output_device', 'index': index}, block=False)
            except Exception:
                pass
        except Exception as e:
            self.window.set_status(f"Failed to set output device: {e}")

    def _set_output_channel_mapping(self, mapping: Optional[list]) -> None:
        """Set custom output channel mapping for mono playback (None means default)."""
        try:
            self.settings_manager.update_setting('output_channel_mapping', mapping)
            label = "Device default" if mapping is None else f"Output channel: {mapping[0]+1 if mapping else ''}"
            self.window.set_status(label)
        except Exception as e:
            self.window.set_status(f"Failed to set output channels: {e}")
        # Propagate mapping to playback process
        try:
            self.playback_queue.put({'action': 'set_output_channel_mapping', 'mapping': mapping}, block=False)
        except Exception:
            pass


    def _delete_current_recording(self) -> None:
        """Delete the current recording take."""
        # Stop any playback first
        sd.stop()
        self._stop_synchronized_playback()
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

    def _stop_synchronized_playback(self) -> None:
        """Stop synchronized playback."""
        self.playback_queue.put({'action': 'stop'})
        # Also reset level meter when playback stops
        if hasattr(self.window, 'embedded_level_meter') and self.window.embedded_level_meter:
            try:
                self.window.embedded_level_meter.reset()
            except Exception:
                pass

    def _start_playback_level_monitoring(self, filepath) -> None:
        """Start monitoring audio levels during playback.

        Args:
            filepath: Path to the audio file being played
        """
        # This is a placeholder for level monitoring during playback
        # The actual implementation would need to monitor the shared state
        # or audio output to update the level meter
        pass

    def _quit(self) -> None:
        """Clean shutdown of the application."""
        print("Shutting down...")

        # Save window geometry if not fullscreen
        if not self.root.attributes('-fullscreen'):
            self.settings_manager.update_setting('window_geometry', self.root.geometry())

        # Stop recording if active
        if self.state.recording.is_recording:
            self._stop_recording()

        # Stop monitoring if active
        if self.is_monitoring:
            self._stop_monitoring_mode()

        # Stop audio queue processing (guard manager might be gone)
        try:
            self.manager_dict['audio_queue_active'] = False
        except Exception:
            pass

        # Stop any playback monitoring
        if hasattr(self, '_playback_monitor_active'):
            self._playback_monitor_active = False

        # Clean up struct shared state
        if hasattr(self, 'shared_state'):
            try:
                self.shared_state.close()
            except Exception:
                pass
            try:
                self.shared_state.unlink()
            except Exception:
                pass

        # Wait for audio transfer thread to finish
        if hasattr(self, 'transfer_thread') and self.transfer_thread.is_alive():
            self.transfer_thread.join(timeout=0.5)

        # Stop processes
        try:
            self.record_queue.put({'action': 'quit'}, block=False)
        except Exception as e:
            print(f"record_queue.put quit failed: {e}")
        try:
            self.playback_queue.put({'action': 'quit'}, block=False)
        except Exception as e:
            print(f"playback_queue.put quit failed: {e}")

        # Signal shutdown to child loops that might be waiting on empty queues
        try:
            self.shutdown_event.set()
        except Exception as e:
            print(f"setting shutdown_event failed: {e}")

        # Wait for processes to finish
        self.record_process.join(timeout=2)
        self.playback_process.join(timeout=2)

        # Terminate if still alive
        if self.record_process.is_alive():
            self.record_process.terminate()
        if self.playback_process.is_alive():
            self.playback_process.terminate()

        # Attempt a final join
        self.record_process.join(timeout=0.5)
        self.playback_process.join(timeout=0.5)

        # Force kill if absolutely necessary
        try:
            if self.record_process.is_alive() and hasattr(self.record_process, 'kill'):
                self.record_process.kill()
        except Exception as e:
            print(f"kill record_process failed: {e}")
        try:
            if self.playback_process.is_alive() and hasattr(self.playback_process, 'kill'):
                self.playback_process.kill()
        except Exception as e:
            print(f"kill playback_process failed: {e}")

        # Clean up all shared memory buffers after processes are done
        if hasattr(self, 'buffer_manager'):
            self.buffer_manager.cleanup_all(wait_time=0.15)

        # Close queues and manager
        try:
            self.record_queue.close()
            self.playback_queue.close()
        except Exception:
            pass
        try:
            self.manager.shutdown()
        except Exception:
            pass

        # Close UI and force-exit as last resort to avoid deadlocks
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def run(self) -> None:
        """Run the application."""
        self.window.focus_window()
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
    """Main entry point for the Revoxx application.

    Sets up multiprocessing for macOS compatibility, parses command line
    arguments, creates configuration, and launches the recorder application.
    Handles special modes like --show-devices for listing audio devices.
    """
    # Multiprocessing setup for macOS
    if platform.system() == 'Darwin':
        mp.set_start_method('spawn', force=True)

    # Set up signal handler for clean shutdown
    def signal_handler(signum, frame):
        print("\nReceived interrupt signal, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

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
    app = Revoxx(config, script_file, recording_dir, debug=args.debug)

    # Set starting index
    app.state.recording.current_index = args.start_idx

    # Run
    app.run()


if __name__ == '__main__':
    main()