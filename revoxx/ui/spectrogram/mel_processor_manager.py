"""Manager for coordinating mel processor updates across components."""

from typing import Tuple
import numpy as np

from ...audio.mel_factory import MelProcessorFactory
from ...audio.processors import MelSpectrogramProcessor
from .display_utils import create_empty_spectrogram


class MelProcessorManager:
    """Manages mel processor updates and coordinates changes across components.

    This class centralizes the complex update logic when sample rates change,
    ensuring all dependent components are properly synchronized.
    """

    def __init__(self, initial_sample_rate: int, fmin: float):
        """Initialize the mel processor manager.

        Args:
            initial_sample_rate: Initial sample rate in Hz
            fmin: Minimum frequency in Hz
        """
        self.current_sample_rate = initial_sample_rate
        self.fmin = fmin

        # Create initial processor
        self.mel_processor, self.n_mels = MelProcessorFactory.create_for_sample_rate(
            initial_sample_rate, fmin
        )

        # Track recording-specific parameters
        self.recording_sample_rate = initial_sample_rate
        self.recording_n_mels = self.n_mels
        self.recording_fmax = initial_sample_rate / 2

    def update_sample_rate(
        self, new_sample_rate: int
    ) -> Tuple[MelSpectrogramProcessor, int, dict]:
        """Update mel processor for a new sample rate.

        Args:
            new_sample_rate: New sample rate in Hz

        Returns:
            Tuple of (new_processor, new_n_mels, update_info)
            where update_info contains:
                - old_n_mels: Previous number of mel bins
                - needs_display_update: Whether display needs updating
                - params: All calculated parameters
        """
        old_n_mels = self.n_mels
        self.current_sample_rate

        # Check if update is needed
        if new_sample_rate == self.current_sample_rate:
            return (
                self.mel_processor,
                self.n_mels,
                {
                    "old_n_mels": old_n_mels,
                    "needs_display_update": False,
                    "params": MelProcessorFactory.calculate_adaptive_params(
                        new_sample_rate, self.fmin
                    ),
                },
            )

        # Create new processor
        new_processor, new_n_mels = MelProcessorFactory.create_for_sample_rate(
            new_sample_rate, self.fmin
        )

        # Get parameters for additional info
        params = MelProcessorFactory.calculate_adaptive_params(
            new_sample_rate, self.fmin
        )

        # Update internal state
        self.mel_processor = new_processor
        self.n_mels = new_n_mels
        self.current_sample_rate = new_sample_rate

        # Update recording parameters
        self.recording_sample_rate = new_sample_rate
        self.recording_n_mels = new_n_mels
        self.recording_fmax = params["fmax"]

        return (
            new_processor,
            new_n_mels,
            {
                "old_n_mels": old_n_mels,
                "needs_display_update": (old_n_mels != new_n_mels),
                "params": params,
            },
        )

    def create_empty_display(self, spec_frames: int) -> np.ndarray:
        """Create empty display data with current mel configuration.

        Args:
            spec_frames: Number of spectrogram frames

        Returns:
            Empty spectrogram array
        """
        return create_empty_spectrogram(self.n_mels, spec_frames)

    def get_recording_params(self) -> dict:
        """Get current recording parameters.

        Returns:
            Dictionary with recording_n_mels, recording_sample_rate, recording_fmax
        """
        return {
            "n_mels": self.recording_n_mels,
            "sample_rate": self.recording_sample_rate,
            "fmax": self.recording_fmax,
        }

    def reset_to_default(self, default_sample_rate: int) -> None:
        """Reset to default configuration.

        Args:
            default_sample_rate: Default sample rate to reset to
        """
        self.mel_processor, self.n_mels = MelProcessorFactory.create_for_sample_rate(
            default_sample_rate, self.fmin
        )
        self.current_sample_rate = default_sample_rate
        self.recording_sample_rate = default_sample_rate
        self.recording_n_mels = self.n_mels
        self.recording_fmax = default_sample_rate / 2
