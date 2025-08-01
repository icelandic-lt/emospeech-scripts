"""Threaded audio recording for better integration with UI."""

import threading
import queue
import sounddevice as sd
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, Callable

from ..constants import AudioConstants
from ..utils.config import AudioConfig


class ThreadedAudioRecorder:
    """Audio recorder using threading instead of multiprocessing for better UI integration."""

    def __init__(self,
                 config: AudioConfig,
                 audio_callback: Optional[Callable[[np.ndarray], None]] = None):
        """Initialize the threaded audio recorder.

        Args:
            config: Audio configuration
            audio_callback: Optional callback for real-time audio processing
        """
        self.config = config
        self.audio_callback = audio_callback

        # Recording state
        self.is_recording = False
        self.audio_data = []

        # Thread-safe queue for audio data
        self.audio_queue = queue.Queue()

        # Configure sounddevice
        self._configure_audio_device()

        # Recording thread
        self.recording_thread = None
        self.stream = None

    def _configure_audio_device(self) -> None:
        """Configure audio device settings."""
        if self.config.input_device is not None:
            sd.default.device[0] = self.config.input_device

        sd.default.samplerate = self.config.sample_rate
        sd.default.channels = self.config.channels
        sd.default.dtype = self.config.dtype

    def start_recording(self) -> None:
        """Start audio recording."""
        if self.is_recording:
            return

        self.is_recording = True
        self.audio_data = []

        # Start recording stream
        self.stream = sd.InputStream(
            callback=self._audio_callback_internal,
            blocksize=AudioConstants.AUDIO_CHUNK_SIZE,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype
        )
        self.stream.start()
        print(f"ThreadedRecorder: Recording started, sr={self.config.sample_rate}, bits={self.config.bit_depth}")

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return audio data."""
        if not self.is_recording:
            return np.array([])

        self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Concatenate all audio chunks
        if self.audio_data:
            total_chunks = len(self.audio_data)
            total_samples = sum(len(chunk) for chunk in self.audio_data)
            duration = total_samples / self.config.sample_rate
            print(f"[DEBUG ThreadedRecorder] Stop: Total chunks: {total_chunks}, total samples: {total_samples}, duration: {duration:.2f}s")
            return np.concatenate(self.audio_data)
        return np.array([])

    def _audio_callback_internal(self, indata: np.ndarray, frames: int,
                                 time_info, status: sd.CallbackFlags) -> None:
        """Internal audio stream callback."""
        if status:
            print(f"Audio callback status: {status}")

        if self.is_recording:
            # Store audio data
            self.audio_data.append(indata.copy())

            # Debug: Track chunks
            if len(self.audio_data) <= 5:
                print(f"[DEBUG Recorder] Stored chunk {len(self.audio_data)}: shape={indata.shape}")

            # Call external callback if provided
            if self.audio_callback:
                try:
                    self.audio_callback(indata.copy())
                except Exception as e:
                    print(f"Error in audio callback: {e}")

    def save_recording(self, audio_data: np.ndarray, filepath: Path) -> None:
        """Save audio data to file."""
        if len(audio_data) == 0:
            print("Warning: No audio data to save")
            return

        print(f"Saving audio: shape={audio_data.shape}, dtype={audio_data.dtype}")
        print(f"Raw min/max: {np.min(audio_data)} / {np.max(audio_data)}")
        print(f"Samples: {len(audio_data)}, frames: {(len(audio_data) - AudioConstants.N_FFT) // AudioConstants.HOP_LENGTH + 1}")

        sf.write(
            str(filepath),
            audio_data,
            self.config.sample_rate,
            subtype=self.config.subtype
        )
        print(f"Recording saved to {filepath}")

    def is_active(self) -> bool:
        """Check if recording is active."""
        return self.is_recording and self.stream is not None