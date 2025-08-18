"""Display handler for loaded recordings."""

from typing import Tuple, List
import numpy as np
from scipy import interpolate

from ...constants import AudioConstants
from ...audio.processors import MelSpectrogramProcessor, ClippingDetector
from ...audio.mel_factory import MelProcessorFactory
from .controllers import ClippingVisualizer, ZoomController


class RecordingDisplay:
    """Handles display of loaded recordings in the spectrogram.

    Manages:
    - Processing complete recordings for display
    - Adaptive mel processing for different sample rates
    - Clipping detection in recordings
    - Zoom and scroll for long recordings
    """

    def __init__(
        self,
        clipping_detector: ClippingDetector,
        clipping_visualizer: ClippingVisualizer,
        zoom_controller: ZoomController,
        spec_frames: int,
        display_config,
    ):
        """Initialize recording display handler.

        Args:
            clipping_detector: Clipping detection processor
            clipping_visualizer: Clipping marker visualizer
            zoom_controller: Zoom state controller
            spec_frames: Number of display frames
            display_config: Display configuration
        """
        self.clipping_detector = clipping_detector
        self.clipping_visualizer = clipping_visualizer
        self.zoom_controller = zoom_controller
        self.spec_frames = spec_frames
        self.display_config = display_config

        # Recording data
        self.all_spec_frames: List[np.ndarray] = []
        self.recording_duration = 0.0
        self.max_detected_freq = 0.0

    def process_recording(
        self, audio_data: np.ndarray, sample_rate: int
    ) -> Tuple[np.ndarray, int, float]:
        """Process a complete recording for display.

        Args:
            audio_data: Complete audio signal (normalized -1 to 1)
            sample_rate: Sample rate of the audio

        Returns:
            Tuple of (display_data, adaptive_n_mels, duration)
        """
        # Clear previous data
        self.all_spec_frames = []
        self.clipping_visualizer.clear()

        # Detect clipping in the recording
        clipping_positions = self.clipping_detector.find_clipping_positions(audio_data)
        self.clipping_visualizer.set_clipping_positions(clipping_positions)

        # Create adaptive mel processor for this sample rate
        recording_mel_processor, adaptive_n_mels = self.create_recording_mel_processor(
            sample_rate
        )

        # Process entire recording
        n_frames = (
            1 + (len(audio_data) - AudioConstants.N_FFT) // AudioConstants.HOP_LENGTH
        )

        mel_min = float("inf")
        mel_max = float("-inf")

        # Compute mel spectrogram for entire recording
        mel_spec = np.zeros((adaptive_n_mels, n_frames))
        self.max_detected_freq = 0.0

        for i in range(n_frames):
            start_idx = i * AudioConstants.HOP_LENGTH
            end_idx = start_idx + AudioConstants.N_FFT

            if end_idx <= len(audio_data):
                frame = audio_data[start_idx:end_idx]
                mel_db, _ = recording_mel_processor.process(frame)
                mel_spec[:, i] = mel_db

                # Update min/max tracking
                mel_min = min(mel_min, np.min(mel_db))
                mel_max = max(mel_max, np.max(mel_db))

                # Track maximum frequency
                freq_bins_with_energy = np.where(
                    mel_db
                    > (
                        AudioConstants.DB_MIN
                        + AudioConstants.MAX_FREQ_ENERGY_THRESHOLD_DB
                    )
                )[0]
                if len(freq_bins_with_energy) > 0:
                    max_bin = freq_bins_with_energy[-1]
                    max_freq = recording_mel_processor.mel_frequencies[max_bin]
                    # Limit to Nyquist frequency
                    max_freq = min(max_freq, sample_rate / 2)
                    self.max_detected_freq = max(self.max_detected_freq, max_freq)

        # Store all frames for zoom
        for i in range(n_frames):
            self.all_spec_frames.append(mel_spec[:, i])

        # Calculate duration
        duration = len(audio_data) / sample_rate
        self.recording_duration = duration
        self.zoom_controller.set_recording_duration(duration)

        # Reset zoom
        self.zoom_controller.reset()

        # Resample if needed for display
        display_data = self.resample_spectrogram_for_display(
            mel_spec, n_frames, adaptive_n_mels
        )
        return display_data, adaptive_n_mels, duration

    def create_recording_mel_processor(
        self, sample_rate: int
    ) -> Tuple[MelSpectrogramProcessor, int]:
        """Create mel processor optimized for recording's sample rate."""
        return MelProcessorFactory.create_for_sample_rate(
            sample_rate, self.display_config.fmin
        )

    def resample_spectrogram_for_display(
        self, mel_spec: np.ndarray, n_frames: int, n_mels: int
    ) -> np.ndarray:
        """Resample spectrogram to fit display width if needed."""
        if n_frames != self.spec_frames:
            # Resample to fit display
            x_old = np.linspace(0, 1, n_frames)
            x_new = np.linspace(0, 1, self.spec_frames)

            resampled = np.zeros((n_mels, self.spec_frames))
            for i in range(n_mels):
                f = interpolate.interp1d(
                    x_old, mel_spec[i, :], kind="linear", fill_value="extrapolate"
                )
                resampled[i, :] = f(x_new)

            return resampled
        elif mel_spec.shape[1] < self.spec_frames:
            # Pad with minimum values if needed
            padded = np.ones((n_mels, self.spec_frames)) * AudioConstants.DB_MIN
            padded[:, : mel_spec.shape[1]] = mel_spec
            return padded
        else:
            return mel_spec[:, : self.spec_frames]

    def get_visible_frames(self, start_frame: int, end_frame: int) -> List[np.ndarray]:
        """Get frames in the visible range.

        Args:
            start_frame: First frame index
            end_frame: Last frame index

        Returns:
            List of frame arrays
        """
        if start_frame < len(self.all_spec_frames):
            return self.all_spec_frames[start_frame:end_frame]
        return []

    def calculate_visible_frame_range(self) -> Tuple[int, int]:
        """Calculate visible frame range based on zoom and offset.

        Returns:
            Tuple of (start_frame, end_frame)
        """
        if not self.all_spec_frames or self.recording_duration <= 0:
            return 0, 0

        visible_seconds = self.recording_duration / self.zoom_controller.zoom_level
        total_frames = len(self.all_spec_frames)
        frames_per_second = total_frames / self.recording_duration

        start_frame = int(self.zoom_controller.view_offset * frames_per_second)
        end_frame = int(
            (self.zoom_controller.view_offset + visible_seconds) * frames_per_second
        )
        end_frame = min(end_frame, total_frames)

        return start_frame, end_frame

    def clear(self) -> None:
        """Clear all recording data."""
        self.all_spec_frames = []
        self.recording_duration = 0.0
        self.max_detected_freq = 0.0
        # Also ensure any recording-time clipping markers are cleared
        self.clipping_visualizer.clear()
