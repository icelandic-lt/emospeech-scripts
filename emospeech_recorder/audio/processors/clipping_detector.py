"""Clipping detection processor."""

from typing import List
import numpy as np

from .processor_base import AudioProcessor
from ...constants import AudioConstants
from ...utils.audio_utils import normalize_audio


class ClippingDetector(AudioProcessor[bool]):
    """Detects clipping in audio signals.

    This processor analyzes audio data to detect clipping (signal saturation)
    which occurs when the audio level exceeds the maximum representable value.
    Clipping detection is useful for monitoring recording quality.

    Attributes:
        threshold: Normalized threshold for clipping detection (0.0 to 1.0)
    """

    def __init__(
        self,
        sample_rate: int = AudioConstants.DEFAULT_SAMPLE_RATE,
        threshold: float = AudioConstants.CLIPPING_THRESHOLD,
    ):
        """Initialize the clipping detector.

        Args:
            sample_rate: Audio sample rate in Hz
            threshold: Clipping threshold (0.95 = 95% of max level)
        """
        super().__init__(sample_rate)
        self.threshold = threshold

    def process(self, audio_data: np.ndarray) -> bool:
        """Check if audio data contains clipping.

        Args:
            audio_data: Audio samples (normalized or raw)

        Returns:
            bool: True if clipping is detected, False otherwise

        Note:
            Handles both normalized (-1 to 1) and raw audio data
        """
        audio_norm = normalize_audio(audio_data)
        max_val = np.max(np.abs(audio_norm))
        return max_val >= self.threshold

    def find_clipping_positions(
        self,
        audio_data: np.ndarray,
        hop_length: int = AudioConstants.HOP_LENGTH,
        chunk_size: int = AudioConstants.AUDIO_CHUNK_SIZE,
    ) -> List[int]:
        """Find all clipping positions in audio data.

        Scans through audio in chunks to find positions where clipping occurs.
        Used for visual indication in spectrograms.

        Args:
            audio_data: Audio samples to analyze
            hop_length: Hop size for frame positioning
            chunk_size: Size of chunks to analyze

        Returns:
            List[int]: Frame positions where clipping is detected

        Note:
            Positions are spaced to avoid overlapping markers in visualization
        """
        clipping_positions = []

        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i : i + chunk_size]
            if len(chunk) > 0 and self.process(chunk):
                frame_pos = i // hop_length

                # Avoid duplicate markers too close together
                if (
                    not clipping_positions
                    or frame_pos - clipping_positions[-1]
                    > AudioConstants.MIN_CLIPPING_MARKER_DISTANCE
                ):
                    clipping_positions.append(frame_pos)

        return clipping_positions
