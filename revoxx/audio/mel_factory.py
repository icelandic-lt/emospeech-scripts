"""Factory for creating mel spectrogram processors."""

from typing import Tuple
from .processors import MelSpectrogramProcessor
from .mel_constants import MEL_CONSTANTS
from ..constants import AudioConstants


class MelProcessorFactory:
    """Factory for creating mel spectrogram processors with adaptive parameters."""

    @staticmethod
    def create_for_sample_rate(
        sample_rate: int, fmin: float = AudioConstants.FMIN
    ) -> Tuple[MelSpectrogramProcessor, int]:
        """Create mel processor adapted to specific sample rate.

        Args:
            sample_rate: Target sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Tuple of (processor, n_mels) where n_mels is the adaptive bin count
        """
        # Use centralized calculation
        params = MEL_CONSTANTS.calculate_adaptive_params(sample_rate, fmin)

        # Create processor
        processor = MelSpectrogramProcessor(
            sample_rate=sample_rate,
            n_mels=params["n_mels"],
            fmin=fmin,
            fmax=params["fmax"],
        )

        return processor, params["n_mels"]

    @staticmethod
    def calculate_adaptive_params(
        sample_rate: int, fmin: float = AudioConstants.FMIN
    ) -> dict:
        """Calculate adaptive parameters without creating processor.

        This method now delegates to the centralized calculation.

        Args:
            sample_rate: Target sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Dict with keys: n_mels, fmax, freq_range, nyquist, scale_factor
        """
        return MEL_CONSTANTS.calculate_adaptive_params(sample_rate, fmin)
