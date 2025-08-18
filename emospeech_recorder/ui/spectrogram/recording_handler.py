"""Handler for live recording functionality."""

import numpy as np
from typing import List

from ...constants import AudioConstants, UIConstants
from ...audio.processors import MelSpectrogramProcessor, ClippingDetector
from ...utils.audio_utils import ensure_mono_normalized
from .controllers import ClippingVisualizer


class RecordingHandler:
    """Handles live recording operations for the spectrogram display.

    Manages:
    - Audio buffer updates
    - Real-time mel spectrogram computation
    - Clipping detection during recording
    - Frame accumulation for zoom/playback
    """

    def __init__(
        self,
        mel_processor: MelSpectrogramProcessor,
        clipping_detector: ClippingDetector,
        clipping_visualizer: ClippingVisualizer,
        spec_frames: int,
        n_mels: int,
        sample_rate: int,
    ):
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
        """Set spec_frames."""
        if value != self._spec_frames:
            self._spec_frames = value

    def configure_for_sample_rate(self, sample_rate: int) -> None:
        """Configure the handler for a new sample rate.

        Args:
            sample_rate: The new sample rate
        """
        self.sample_rate = sample_rate
        self.frames_per_second = sample_rate / AudioConstants.HOP_LENGTH
        self.buffer_size = int(UIConstants.SPECTROGRAM_DISPLAY_SECONDS * sample_rate)
        self.audio_buffer = np.zeros(self.buffer_size)
        self.buffer_position = 0

    def start_recording(self) -> None:
        """Start recording mode."""
        self.is_recording = True
        self.frame_count = 0
        self.update_counter = 0
        # Always reset clipping markers at start of live mode
        self.clipping_visualizer.clear()
        self.max_detected_freq = 0.0
        self.all_spec_frames = []

        # Clear audio buffer
        self.audio_buffer.fill(0)
        self.buffer_position = 0

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

        audio_chunk = ensure_mono_normalized(audio_chunk)
        chunk_size = len(audio_chunk)

        # Add new audio to buffer
        if self.buffer_position + chunk_size <= self.buffer_size:
            self.audio_buffer[
                self.buffer_position : self.buffer_position + chunk_size
            ] = audio_chunk
        else:
            # Shift buffer left by the overflow amount
            self.audio_buffer[:-chunk_size] = self.audio_buffer[chunk_size:]
            # Add new chunk at the end
            self.audio_buffer[-chunk_size:] = audio_chunk
            # Adjust buffer position
            self.buffer_position = self.buffer_size - chunk_size

        # Process complete frames
        frames_processed = False
        frame_start = 0
        # Process all complete frames in the buffer
        while frame_start + AudioConstants.N_FFT <= self.buffer_position + chunk_size:
            # Extract frame for processing
            frame_end = frame_start + AudioConstants.N_FFT
            frame = self.audio_buffer[frame_start:frame_end]

            # Detect clipping
            if self.clipping_detector.process(frame):
                clipping_pos = self.frame_count
                current_markers = self.clipping_visualizer.clipping_markers
                if (
                    not current_markers
                    or clipping_pos - current_markers[-1]
                    > AudioConstants.MIN_CLIPPING_MARKER_DISTANCE
                ):
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

            # Store frame for zoom/scroll
            self.all_spec_frames.append(mel_db.copy())
            self.frame_count += 1

            # Move to next frame position
            frame_start += AudioConstants.HOP_LENGTH
            frames_processed = True

        # Update buffer position to point after the new chunk
        self.buffer_position += chunk_size

        # Remove processed data from buffer if needed
        if frame_start > 0:
            # Shift unprocessed data to the beginning
            remaining = self.buffer_position - frame_start
            if remaining > 0:
                self.audio_buffer[:remaining] = self.audio_buffer[
                    frame_start : self.buffer_position
                ]
            self.buffer_position = remaining

        # Update current time
        self.current_time = (
            self.frame_count * AudioConstants.HOP_LENGTH
        ) / self.sample_rate

        # Throttle UI updates
        self.update_counter += 1
        target_ui_fps = 1000.0 / UIConstants.ANIMATION_UPDATE_MS
        ui_update_interval = max(1, int(self.frames_per_second / target_ui_fps))

        should_update = frames_processed and (
            self.update_counter % ui_update_interval == 0
        )
        return should_update

    def clear(self) -> None:
        """Clear all recording data."""
        self.audio_buffer.fill(0)
        self.clipping_visualizer.clear()
        self.max_detected_freq = 0.0
        self.all_spec_frames = []
        self.frame_count = 0
        self.update_counter = 0
        self.current_time = 0
