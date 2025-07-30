"""Handler for live recording functionality."""

import queue
import numpy as np
from typing import Optional, List

from ...constants import AudioConstants, UIConstants
from ...audio.processor import MelSpectrogramProcessor, ClippingDetector
from .controllers import ClippingVisualizer


class RecordingHandler:
    """Handles live recording operations for the spectrogram display.

    Manages:
    - Audio buffer updates
    - Real-time mel spectrogram computation
    - Clipping detection during recording
    - Frame accumulation for zoom/playback
    """

    def __init__(self, mel_processor: MelSpectrogramProcessor,
                 clipping_detector: ClippingDetector,
                 clipping_visualizer: ClippingVisualizer,
                 spec_frames: int, n_mels: int, sample_rate: int):
        """Initialize recording handler.

        Args:
            mel_processor: Mel spectrogram processor
            clipping_detector: Clipping detection processor
            clipping_visualizer: Clipping marker visualizer
            spec_frames: Number of display frames
            n_mels: Number of mel bins
            sample_rate: Audio sample rate
        """
        self.mel_processor = mel_processor
        self.clipping_detector = clipping_detector
        self.clipping_visualizer = clipping_visualizer
        self._spec_frames = spec_frames
        self.n_mels = n_mels
        self.sample_rate = sample_rate

        # Calculate frame rate
        self.frames_per_second = sample_rate / AudioConstants.HOP_LENGTH

        # Audio buffer for spectrogram computation
        self.buffer_size = int(UIConstants.SPECTROGRAM_DISPLAY_SECONDS * sample_rate)
        self.audio_buffer = np.zeros(self.buffer_size)
        self.buffer_position = 0

        # Spectrogram display buffer
        self.spec_buffer = np.ones((n_mels, self._spec_frames)) * AudioConstants.DB_MIN

        # Thread-safe queue for audio data
        self.audio_queue = queue.Queue(maxsize=100)

        # Recording state
        self.is_recording = False
        self.frame_count = 0
        self.update_counter = 0
        self.pending_update = False

        # Time tracking
        self.recording_start_time = 0
        self.current_time = 0

        # Store all frames for zoom/scroll
        self.all_spec_frames: List[np.ndarray] = []

        # Frequency detection
        self.max_detected_freq = 0.0

    @property
    def spec_frames(self) -> int:
        """Get spec_frames."""
        return self._spec_frames

    @spec_frames.setter
    def spec_frames(self, value: int) -> None:
        """Set spec_frames and resize buffer."""
        if value != self._spec_frames:
            self._spec_frames = value
            # Resize spec buffer preserving data
            old_buffer = self.spec_buffer
            self.spec_buffer = np.ones((self.n_mels, value)) * AudioConstants.DB_MIN
            # Copy existing data
            copy_frames = min(old_buffer.shape[1], value)
            self.spec_buffer[:, -copy_frames:] = old_buffer[:, -copy_frames:]

    def start_recording(self) -> None:
        """Start recording mode."""
        self.is_recording = True
        self.frame_count = 0
        self.update_counter = 0
        self.clipping_visualizer.clear()
        self.max_detected_freq = 0.0
        self.all_spec_frames = []

    def stop_recording(self) -> None:
        """Stop recording mode."""
        self.is_recording = False

    def update_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process incoming audio chunk.

        Args:
            audio_chunk: New audio samples

        Returns:
            True if display should be updated
        """
        if not self.is_recording:
            return False

        chunk_size = len(audio_chunk)

        # Update audio buffer (rolling buffer)
        if self.buffer_position + chunk_size <= self.buffer_size:
            self.audio_buffer[self.buffer_position:self.buffer_position + chunk_size] = audio_chunk
        else:
            overflow = (self.buffer_position + chunk_size) - self.buffer_size
            self.audio_buffer[self.buffer_position:] = audio_chunk[:-overflow]
            self.audio_buffer[:overflow] = audio_chunk[-overflow:]

        # Process complete frames
        frames_processed = False
        while self.buffer_position + AudioConstants.N_FFT <= self.buffer_size:
            # Extract frame for processing
            frame_start = self.buffer_position
            frame_end = frame_start + AudioConstants.N_FFT
            frame = self.audio_buffer[frame_start:frame_end]

            # Detect clipping
            clipping_pos = self.clipping_detector.check_frame(frame, self.frame_count)
            if clipping_pos is not None:
                current_markers = self.clipping_visualizer.clipping_markers
                if (not current_markers or
                    clipping_pos - current_markers[-1] > AudioConstants.MIN_CLIPPING_MARKER_DISTANCE):
                    current_markers.append(clipping_pos)
                    self.clipping_visualizer.set_clipping_positions(current_markers)

            # Compute mel spectrogram
            mel_db, _ = self.mel_processor.process(frame)

            # Track maximum frequency content
            freq_bins_with_energy = np.where(mel_db > AudioConstants.DB_MIN + 20)[0]
            if len(freq_bins_with_energy) > 0:
                max_bin = freq_bins_with_energy[-1]
                max_freq = self.mel_processor.mel_frequencies[max_bin]
                self.max_detected_freq = max(self.max_detected_freq, max_freq)

            # Update spectrogram buffer
            self.spec_buffer = np.roll(self.spec_buffer, -1, axis=1)
            self.spec_buffer[:, -1] = mel_db
            self.frame_count += 1

            # Store frame for zoom/scroll
            self.all_spec_frames.append(mel_db.copy())

            # Move position by hop_length
            self.buffer_position += AudioConstants.HOP_LENGTH
            frames_processed = True

        # Adjust buffer position when rolling
        self.buffer_position -= chunk_size

        # Update current time
        self.current_time = (self.frame_count * AudioConstants.HOP_LENGTH) / self.sample_rate

        # Throttle UI updates
        self.update_counter += 1
        target_ui_fps = 1000.0 / UIConstants.ANIMATION_UPDATE_MS
        ui_update_interval = max(1, int(self.frames_per_second / target_ui_fps))

        should_update = frames_processed and (self.update_counter % ui_update_interval == 0)

        return should_update

    def get_current_spec_buffer(self) -> np.ndarray:
        """Get current spectrogram buffer for display."""
        return self.spec_buffer

    def clear(self) -> None:
        """Clear all recording data."""
        self.spec_buffer.fill(AudioConstants.DB_MIN)
        self.audio_buffer.fill(0)
        self.clipping_visualizer.clear()
        self.max_detected_freq = 0.0
        self.all_spec_frames = []
        self.frame_count = 0
        self.update_counter = 0
        self.current_time = 0