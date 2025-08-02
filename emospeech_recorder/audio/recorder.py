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
from ..utils.config import AudioConfig
from ..utils.audio_utils import calculate_blocksize


class AudioRecorder:
    """Audio recorder with struct-based synchronized position updates."""

    def __init__(self, config: AudioConfig, shared_state_name: str,
                 audio_queue: Optional[mp.Queue] = None):
        """Initialize synchronized audio recorder.

        Args:
            config: Audio configuration
            shared_state_name: Name of shared memory block
            audio_queue: Optional queue for sending audio to visualization
        """
        self.config = config
        self.audio_queue = audio_queue

        # Attach to existing shared state
        self.shared_state = SharedState(create=False)
        self.shared_state.attach_to_existing(shared_state_name)

        # Recording state
        self.is_recording = False
        self.audio_chunks = []
        self.stream: Optional[sd.InputStream] = None
        self.current_position = 0

        # Calculate blocksize from response time setting
        self.blocksize = calculate_blocksize(
            config.sync_response_time_ms,
            config.sample_rate
        )

    def start_recording(self) -> None:
        """Start synchronized recording."""
        # First check recording state
        recording_state = self.shared_state.get_recording_state()
        if recording_state.get('status', 0) == SHARED_STATUS_INVALID:
            print("ERROR: Recording state not initialized", file=sys.stderr)
            return

        # Read current audio settings from shared state
        settings = self.shared_state.get_audio_settings()

        # Check if settings are properly initialized
        if settings.get('status', 0) == SHARED_STATUS_INVALID:
            print("ERROR: Audio settings not initialized (invalid status)", file=sys.stderr)
            print(f"ERROR: Settings: {settings}", file=sys.stderr)
            return

        sample_rate = settings['sample_rate']

        # Update config if settings changed
        if sample_rate != self.config.sample_rate:
            print(f"Recording: Updating sample rate from {self.config.sample_rate} to {sample_rate}")
            self.config.sample_rate = sample_rate
            # Recalculate blocksize
            self.blocksize = calculate_blocksize(
                self.config.sync_response_time_ms,
                sample_rate
            )

        # Reset state
        self.is_recording = True
        self.audio_chunks = []
        self.current_position = 0

        # Update shared state
        self.shared_state.start_recording(sample_rate)

        # Create input stream with callback
        self.stream = sd.InputStream(
            samplerate=sample_rate,
            blocksize=self.blocksize,
            device=self.config.input_device,
            channels=self.config.channels,
            dtype=self.config.dtype,
            callback=self._audio_callback
        )

        self.stream.start()
        print(f"Started recording: {sample_rate}Hz, blocksize={self.blocksize}")

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

        # Check if settings are properly initialized
        if settings.get('status', 0) == SHARED_STATUS_INVALID:
            print("ERROR: Audio settings not initialized in save_recording (invalid status)", file=sys.stderr)
            return

        sample_rate = settings['sample_rate']
        bit_depth = settings['bit_depth']

        # Determine subtype based on format and bit depth
        if filepath.suffix.lower() == '.flac':
            # For FLAC, explicitly set subtype based on bit depth
            if bit_depth == 24:
                sf.write(str(filepath), audio_data, sample_rate, subtype='PCM_24')
            else:
                sf.write(str(filepath), audio_data, sample_rate, subtype='PCM_16')
        elif self.config.subtype:
            # For WAV files, use configured subtype
            sf.write(str(filepath), audio_data, sample_rate, subtype=self.config.subtype)
        else:
            # Default behavior
            sf.write(str(filepath), audio_data, sample_rate)

    def _audio_callback(self, indata: np.ndarray, frames: int,
                       time_info, status) -> None:
        """Audio stream callback with hardware timing.

        Args:
            indata: Input buffer with audio data
            frames: Number of frames received
            time_info: Hardware timing information
            status: Callback status flags
        """
        if status:
            print(f"Recording callback status: {status}")

        if self.is_recording:
            # Store audio chunk
            self.audio_chunks.append(indata.copy())

            # Update shared state with hardware timing
            self.shared_state.update_recording_position(
                self.current_position,
                time_info.inputBufferAdcTime
            )

            # Send to visualization queue if active
            if self.audio_queue and self.shared_state.shm:
                # Check if audio queue is active (from shared dict if available)
                try:
                    self.audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    pass  # Skip if queue is full

            # Update position
            self.current_position += frames

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.shared_state:
            self.shared_state.close()


def record_process(config: AudioConfig,
                   audio_queue: mp.Queue,
                   shared_state_name: str,
                   control_queue: mp.Queue,
                   manager_dict: dict) -> None:
    """Process function for audio recording with hardware synchronization.

    Args:
        config: Audio configuration
        audio_queue: Queue for audio visualization
        shared_state_name: Name of shared memory block
        control_queue: Queue for control commands
        manager_dict: Shared manager dict (for save_path compatibility)
    """
    recorder = None

    try:
        # Create recorder with shared state
        recorder = AudioRecorder(config, shared_state_name, audio_queue)

        while True:
            try:
                command = control_queue.get(timeout=0.1)

                if command == 'start':
                    recorder.start_recording()

                elif command == 'stop':
                    audio_data = recorder.stop_recording()

                    # Get save path from old shared state (for compatibility)
                    save_path = manager_dict.get('save_path')
                    if save_path and len(audio_data) > 0:
                        recorder.save_recording(audio_data, Path(save_path))
                        print(f"Recording saved to {save_path}")

                    # Clear save path
                    manager_dict['save_path'] = None

                elif command == 'quit':
                    break

            except queue.Empty:
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