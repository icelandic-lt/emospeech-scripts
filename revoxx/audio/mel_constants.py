"""Central configuration for mel spectrogram parameters."""

from dataclasses import dataclass
import numpy as np


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
    MAX_N_MELS: int = 110

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

        # Adaptive fmax calculation to prevent empty mel filters
        if sample_rate <= 48000:
            # For standard rates, use BASE_FMAX or slightly below Nyquist
            fmax = min(nyquist - 1000, cls.BASE_FMAX)
        else:
            # For high sample rates, use 48% of sample rate to ensure valid mel filters
            # This prevents empty filter banks at frequencies like 192kHz
            fmax = sample_rate * 0.48

        # Ensure fmax doesn't exceed Nyquist (with some margin)
        fmax = min(fmax, nyquist - 100)

        freq_range = fmax - fmin

        # Calculate scale factor and adjust n_mels more conservatively for high rates
        if sample_rate <= 48000:
            scale_factor = freq_range / cls.BASE_FREQ_RANGE
            n_mels = max(
                cls.MIN_N_MELS, min(cls.MAX_N_MELS, int(cls.BASE_N_MELS * scale_factor))
            )
        else:
            # For high sample rates, use logarithmic scaling to prevent too many mel bins
            # This ensures mel filters have enough frequency coverage
            scale_factor = np.log2(sample_rate / cls.BASE_SAMPLE_RATE)
            # Keep n_mels moderate to ensure each filter has enough frequency range
            n_mels = min(
                int(cls.BASE_N_MELS * (1 + scale_factor * 0.25)), cls.MAX_N_MELS
            )

        return {
            "nyquist": nyquist,
            "fmax": fmax,
            "freq_range": freq_range,
            "scale_factor": scale_factor,
            "n_mels": n_mels,
        }


# Global instance for easy access
MEL_CONSTANTS = MelConstants()
