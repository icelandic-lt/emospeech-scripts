"""Audio recorder with hardware-synchronized position updates.

This module implements recording with struct-based shared memory
for inter-process communication.
"""

import sys
import numpy as np
import sounddevice as sd
from pathlib import Path
from typing import Optional
import multiprocessing as mp
import queue
import traceback
import soundfile as sf

from .shared_state import SharedState, SHARED_STATUS_INVALID
from .level_calculator import LevelCalculator
from ..utils.config import AudioConfig
from ..utils.audio_utils import calculate_blocksize


class AudioRecorder:
    """Audio recorder with struct-based synchronized position updates."""

    def __init__(
        self,
        config: AudioConfig,
        shared_state_name: str,
        audio_queue: Optional[mp.Queue] = None,
        manager_dict: Optional[dict] = None,
    ):
        """Initialize synchronized audio recorder.

        Args:
            config: Audio configuration
            shared_state_name: Name of shared memory block
            audio_queue: Optional queue for sending audio to visualization
            manager_dict: Shared manager dict
        """
        self.config = config
        self.audio_queue = audio_queue
        self.manager_dict = manager_dict

        # Attach to existing shared state
        self.shared_state = SharedState(create=False)
        self.shared_state.attach_to_existing(shared_state_name)

        # Recording state
        self.is_recording = False
        self.audio_chunks = []
        self.stream: Optional[sd.InputStream] = None
        self.current_position = 0

        # Level calculator for meter updates
        self.level_calculator = LevelCalculator(config.sample_rate)

        # Calculate blocksize from response time setting
        self.blocksize = calculate_blocksize(
            config.sync_response_time_ms, config.sample_rate
        )

    def set_input_device(self, index: Optional[int]) -> None:
        """Update input device index used for future streams."""
        self.config.input_device = index

    def start_recording(self) -> bool:
        """Start synchronized recording.

        Returns:
            bool: True if stream started successfully, False otherwise
        """
        # First check recording state
        recording_state = self.shared_state.get_recording_state()
        if recording_state.get("status", 0) == SHARED_STATUS_INVALID:
            print("ERROR: Recording state not initialized", file=sys.stderr)
            return False

        # Read current audio settings from shared state
        settings = self.shared_state.get_audio_settings()

        # Check if settings are correctly initialized
        if settings.get("status", 0) == SHARED_STATUS_INVALID:
            print(
                "ERROR: Audio settings not initialized (invalid status)",
                file=sys.stderr,
            )
            print(f"ERROR: Settings: {settings}", file=sys.stderr)
            return False

        sample_rate = settings["sample_rate"]

        # Update config if settings changed
        if sample_rate != self.config.sample_rate:
            self.config.sample_rate = sample_rate
            # Update level calculator
            self.level_calculator.update_sample_rate(sample_rate)
            # Recalculate blocksize
            self.blocksize = calculate_blocksize(
                self.config.sync_response_time_ms, sample_rate
            )

        # Reset state
        self.is_recording = True
        self.audio_chunks = []
        self.current_position = 0

        # Update shared state
        self.shared_state.start_recording(sample_rate)

        # Create input stream with callback
        # Support optional input mapping by opening enough channels and selecting in callback
        input_mapping = getattr(self, "_input_channel_mapping", None)
        # Determine available input channels on current device (best-effort)
        max_in_ch = None
        try:
            dev_info = (
                sd.query_devices(self.config.input_device)
                if self.config.input_device is not None
                else sd.query_devices(None)
            )
            max_in_ch = (
                int(dev_info.get("max_input_channels", 0))
                if isinstance(dev_info, dict)
                else None
            )
        except (sd.PortAudioError, ValueError, TypeError, AttributeError):
            pass

        if isinstance(input_mapping, list) and len(input_mapping) > 0:
            # Filter mapping to available channels if known
            if max_in_ch is not None:
                filtered = [int(i) for i in input_mapping if 0 <= int(i) < max_in_ch]
            else:
                filtered = [int(i) for i in input_mapping]
            if len(filtered) == 0:
                # Fallback to default behavior
                self._input_channel_pick = None
                open_channels = self.config.channels
            else:
                self._input_channel_pick = filtered
                open_channels = (
                    min(len(filtered), max_in_ch)
                    if max_in_ch is not None
                    else len(filtered)
                )
        else:
            open_channels = (
                min(self.config.channels, max_in_ch)
                if (max_in_ch is not None and max_in_ch > 0)
                else self.config.channels
            )
            self._input_channel_pick = None

        # Create input stream with fallback to default device if needed
        try:
            self.stream = sd.InputStream(
                samplerate=sample_rate,
                blocksize=self.blocksize,
                device=self.config.input_device,
                channels=open_channels,
                dtype=self.config.dtype,
                callback=self._audio_callback,
            )
        except (sd.PortAudioError, OSError):
            # Try default system input device
            try:
                self.stream = sd.InputStream(
                    samplerate=sample_rate,
                    blocksize=self.blocksize,
                    device=None,  # i.e. System-Default
                    channels=open_channels,
                    dtype=self.config.dtype,
                    callback=self._audio_callback,
                )
            except (sd.PortAudioError, OSError) as e:
                print(f"Error opening InputStream: {e}", file=sys.stderr)
                self.is_recording = False
                # Signal to main process
                if self.manager_dict is not None:
                    try:
                        self.manager_dict["last_input_error"] = str(e)
                    except (KeyError, TypeError):
                        pass
                return False

        self.stream.start()
        return True

    def _process_input_channels(self, indata: np.ndarray) -> np.ndarray:
        """Process input data according to channel mapping configuration.

        Args:
            indata: Raw input data from audio callback

        Returns:
            Processed audio data with appropriate channel selection/mixing
        """
        if not hasattr(self, "_input_channel_pick") or not self._input_channel_pick:
            return indata.copy()

        # Guard indices vs delivered channel count
        available = indata.shape[1] if indata.ndim == 2 else 1
        safe_indices = [i for i in self._input_channel_pick if 0 <= i < available]

        if len(safe_indices) == 0:
            # Fallback to first available channels matching config.channels
            if indata.ndim == 2 and available >= self.config.channels:
                picked = indata[:, : self.config.channels]
            else:
                picked = indata
        else:
            picked = indata[:, safe_indices] if indata.ndim == 2 else indata

        # If more than one channel selected for mono config, average to mono
        if self.config.channels == 1 and picked.ndim == 2 and picked.shape[1] > 1:
            picked = picked.mean(axis=1, keepdims=True).astype(indata.dtype)

        return picked.copy()

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return audio data."""
        self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self.shared_state.stop_recording()

        # Concatenate all chunks
        if self.audio_chunks:
            return np.concatenate(self.audio_chunks)
        return np.array([])

    def save_recording(self, audio_data: np.ndarray, filepath: Path) -> None:
        """Save audio data to file.

        Args:
            audio_data: Audio samples to save
            filepath: Path to save file
        """
        # Get current settings from shared state
        settings = self.shared_state.get_audio_settings()

        # Check if settings are correctly initialized
        if settings.get("status", 0) == SHARED_STATUS_INVALID:
            print(
                "ERROR: Audio settings not initialized in save_recording (invalid status)",
                file=sys.stderr,
            )
            return

        sample_rate = settings["sample_rate"]
        bit_depth = settings["bit_depth"]

        # Determine subtype based on format and bit depth
        if filepath.suffix.lower() == ".flac":
            # For FLAC, explicitly set subtype based on bit depth
            if bit_depth == 24:
                sf.write(str(filepath), audio_data, sample_rate, subtype="PCM_24")
            else:
                sf.write(str(filepath), audio_data, sample_rate, subtype="PCM_16")
        elif self.config.subtype:
            # For WAV files, use configured subtype
            sf.write(
                str(filepath), audio_data, sample_rate, subtype=self.config.subtype
            )
        else:
            # Default behavior
            sf.write(str(filepath), audio_data, sample_rate)

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info, status
    ) -> None:
        """Audio stream callback with hardware timing.

        Args:
            indata: Input buffer with audio data
            frames: Number of frames received
            time_info: Hardware timing information
            status: Callback status flags
        """

        if self.is_recording:
            # Store audio chunk
            try:
                processed_audio = self._process_input_channels(indata)
                self.audio_chunks.append(processed_audio)
            except (ValueError, MemoryError):
                # On any channel/memory error, append zeros to keep timing consistent
                try:
                    zeros = np.zeros_like(indata)
                    self.audio_chunks.append(zeros)
                except MemoryError:
                    pass

            # Update shared state with hardware timing
            self.shared_state.update_recording_position(
                self.current_position, time_info.inputBufferAdcTime
            )

            # Calculate and update level meter
            rms_db, peak_db, peak_hold_db = self.level_calculator.process(
                indata, self.config.channels
            )
            self.shared_state.update_level_meter(
                rms_db=rms_db,
                peak_db=peak_db,
                peak_hold_db=peak_hold_db,
                frame_count=self.level_calculator.get_frame_count(),
            )

            # Send to visualization queue if active
            if self.audio_queue and self.shared_state.shm:
                # Check if audio queue is active (from shared dict if available)
                try:
                    self.audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    pass

            # Update position
            self.current_position += frames

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.shared_state:
            self.shared_state.close()


def record_process(
    config: AudioConfig,
    audio_queue: mp.Queue,
    shared_state_name: str,
    control_queue: mp.Queue,
    manager_dict: dict,
    shutdown_event: mp.Event,
) -> None:
    """Process function for audio recording with hardware synchronization.

    Args:
        config: Audio configuration
        audio_queue: Queue for audio visualization
        shared_state_name: Name of shared memory block
        control_queue: Queue for control commands
        manager_dict: Shared manager dict (for save_path compatibility)
        shutdown_event: Signal for shutting down process
    """
    recorder = None

    try:
        # Create recorder with shared state
        recorder = AudioRecorder(config, shared_state_name, audio_queue)

        while True:
            try:
                command = control_queue.get(timeout=0.1)

                # Only accept dictionary commands for consistency
                if not isinstance(command, dict):
                    print(f"Warning: Received non-dictionary command: {command}")
                    continue

                action = command.get("action")

                if action == "start":
                    recorder.start_recording()

                elif action == "stop":
                    audio_data = recorder.stop_recording()

                    # Get save path from old shared state (for compatibility)
                    save_path = manager_dict.get("save_path")
                    if save_path and len(audio_data) > 0:
                        recorder.save_recording(audio_data, Path(save_path))

                    # Clear save path
                    manager_dict["save_path"] = None

                elif action == "quit":
                    break

                elif action == "set_input_device":
                    # Update device index for future recordings
                    value = command.get("index", None)
                    if isinstance(value, int):
                        recorder.set_input_device(value)
                    elif value is None:
                        recorder.set_input_device(None)

                elif action == "set_input_channel_mapping":
                    # Update mapping for future recordings
                    mapping = command.get("mapping", None)
                    # Store on the recorder instance for future use
                    try:
                        if isinstance(mapping, list):
                            # validate ints
                            mapping = [int(x) for x in mapping]
                            recorder._input_channel_mapping = mapping
                        else:
                            recorder._input_channel_mapping = None
                    except (ValueError, TypeError):
                        recorder._input_channel_mapping = None

                else:
                    print(f"Warning: Unsupported action: {action}")

            except queue.Empty:
                if shutdown_event.is_set():
                    break
                continue
            except KeyboardInterrupt:
                break

    except Exception as e:
        print(f"Record process error: {e}")
        traceback.print_exc()

    finally:
        # Cleanup
        if recorder:
            recorder.cleanup()
        print("Recording process terminated")
