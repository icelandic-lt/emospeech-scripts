"""Factory for creating mel spectrogram processors."""

from typing import Tuple
from .processor import MelSpectrogramProcessor
from ..constants import AudioConstants


class MelProcessorFactory:
    """Factory for creating mel spectrogram processors with adaptive parameters."""

    @staticmethod
    def create_for_sample_rate(sample_rate: int, fmin: float = AudioConstants.FMIN) -> Tuple[MelSpectrogramProcessor, int]:
        """Create mel processor adapted to specific sample rate.

        Args:
            sample_rate: Target sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Tuple of (processor, n_mels) where n_mels is the adaptive bin count
        """
        # Calculate Nyquist frequency
        nyquist_freq = sample_rate / 2
        fmax = nyquist_freq

        # Calculate adaptive mel bins based on frequency range
        # Ensures minimum 80 bins for good resolution
        freq_range = fmax - fmin
        base_range = 24000 - 50  # Reference range for 48kHz sample rate
        mel_scale_factor = freq_range / base_range
        n_mels = max(80, int(96 * mel_scale_factor))

        # Create processor
        processor = MelSpectrogramProcessor(
            sample_rate=sample_rate,
            n_mels=n_mels,
            fmin=fmin,
            fmax=fmax
        )

        return processor, n_mels

    @staticmethod
    def calculate_adaptive_params(sample_rate: int, fmin: float = AudioConstants.FMIN) -> dict:
        """Calculate adaptive parameters without creating processor.

        Args:
            sample_rate: Target sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Dict with keys: n_mels, fmax, freq_range
        """
        nyquist_freq = sample_rate / 2
        fmax = nyquist_freq
        freq_range = fmax - fmin

        # Calculate adaptive bins
        base_range = 24000 - 50
        mel_scale_factor = freq_range / base_range
        n_mels = max(80, int(96 * mel_scale_factor))

        return {
            'n_mels': n_mels,
            'fmax': fmax,
            'freq_range': freq_range,
            'nyquist': nyquist_freq
        }