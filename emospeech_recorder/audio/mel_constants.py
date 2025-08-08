"""Central configuration for mel spectrogram parameters."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MelConstants:
    """Constants for mel spectrogram computation.

    These values define the adaptive scaling behavior for different sample rates.
    """
    # Base parameters (for 48kHz reference)
    BASE_SAMPLE_RATE: int = 48000
    BASE_FMIN: int = 50
    BASE_FMAX: int = 24000
    BASE_N_MELS: int = 96

    # Computed base range
    BASE_FREQ_RANGE: int = BASE_FMAX - BASE_FMIN  # 23950

    # Limits
    MIN_N_MELS: int = 80
    MAX_N_MELS: int = 256

    @classmethod
    def calculate_adaptive_params(cls, sample_rate: int, fmin: float) -> dict:
        """Calculate adaptive mel parameters for a given sample rate.

        This is the single source of truth for adaptive mel bin calculation.

        Args:
            sample_rate: Target sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Dictionary with calculated parameters:
                - nyquist: Nyquist frequency
                - fmax: Maximum frequency (limited by Nyquist)
                - freq_range: Frequency range (fmax - fmin)
                - scale_factor: Scaling factor relative to base
                - n_mels: Number of mel bins (adaptive)
        """
        nyquist = sample_rate / 2
        fmax = min(nyquist, cls.BASE_FMAX)  # Cap at original fmax or Nyquist
        freq_range = fmax - fmin
        scale_factor = freq_range / cls.BASE_FREQ_RANGE
        n_mels = max(cls.MIN_N_MELS, min(cls.MAX_N_MELS, int(cls.BASE_N_MELS * scale_factor)))

        return {
            'nyquist': nyquist,
            'fmax': fmax,
            'freq_range': freq_range,
            'scale_factor': scale_factor,
            'n_mels': n_mels
        }


# Global instance for easy access
MEL_CONSTANTS = MelConstants()