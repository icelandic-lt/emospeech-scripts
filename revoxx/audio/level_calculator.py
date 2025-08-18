"""Level meter calculations for audio monitoring.

This module provides calculation functionality for the Level widget.
"""

import numpy as np
from typing import Tuple
from ..utils.audio_utils import normalize_audio
from ..constants import AudioConstants


class LevelCalculator:
    """Calculates RMS, peak, and peak-hold levels for audio data."""

    # Default window parameters
    DEFAULT_RMS_WINDOW_MS = 300.0  # Default RMS calculation window in milliseconds
    DEFAULT_PEAK_HOLD_MS = 3000.0  # Default peak hold duration in milliseconds

    def __init__(
        self, sample_rate: int, rms_window_ms: float = None, peak_hold_ms: float = None
    ):
        """Initialize level calculator.

        Args:
            sample_rate: Audio sample rate in Hz
            rms_window_ms: RMS calculation window in milliseconds
            peak_hold_ms: Peak hold duration in milliseconds
        """
        self.sample_rate = sample_rate
        self.rms_window_ms = rms_window_ms or self.DEFAULT_RMS_WINDOW_MS
        self.peak_hold_ms = peak_hold_ms or self.DEFAULT_PEAK_HOLD_MS

        # RMS calculation state
        self.rms_window_samples = int(
            self.rms_window_ms * sample_rate / AudioConstants.MS_TO_SEC
        )
        self.audio_buffer = np.zeros(self.rms_window_samples)
        self.buffer_index = 0

        # Peak hold state
        self.peak_hold_db = AudioConstants.MIN_DB_LEVEL
        self.peak_hold_counter = 0
        self.peak_hold_samples = int(
            self.peak_hold_ms * sample_rate / AudioConstants.MS_TO_SEC
        )

        # Frame counter
        self.frame_count = 0

    def update_sample_rate(self, sample_rate: int) -> None:
        """Update sample rate and recalculate parameters.

        Args:
            sample_rate: New sample rate in Hz
        """
        if sample_rate != self.sample_rate:
            self.sample_rate = sample_rate
            # Recalculate window sizes
            new_rms_samples = int(
                self.rms_window_ms * sample_rate / AudioConstants.MS_TO_SEC
            )

            # Resize RMS buffer if needed
            if new_rms_samples != self.rms_window_samples:
                # Create new buffer and copy what fits
                new_buffer = np.zeros(new_rms_samples)
                copy_size = min(new_rms_samples, self.rms_window_samples)
                new_buffer[:copy_size] = self.audio_buffer[:copy_size]

                self.audio_buffer = new_buffer
                self.rms_window_samples = new_rms_samples
                self.buffer_index = min(self.buffer_index, new_rms_samples - 1)

            # Update peak hold samples
            self.peak_hold_samples = int(
                self.peak_hold_ms * sample_rate / AudioConstants.MS_TO_SEC
            )

    def process(
        self, audio_data: np.ndarray, channels: int = 1
    ) -> Tuple[float, float, float]:
        """Process audio data and return level measurements.

        Args:
            audio_data: Audio samples
            channels: Number of channels in audio_data (we only support mono currently)

        Returns:
            Tuple of (rms_db, peak_db, peak_hold_db)
        """
        # Normalize audio data first to ensure correct dB calculation
        normalized_data = normalize_audio(audio_data)

        # Get mono signal for level calculation
        if channels != 1:
            raise ValueError(f"Only mono audio is supported, got {channels} channels")

        # Handle both 1D and 2D arrays for mono
        if normalized_data.ndim == 1:
            mono_data = normalized_data
        elif normalized_data.ndim == 2:
            mono_data = normalized_data[:, 0]
        else:
            raise ValueError(f"Unexpected array dimensions: {normalized_data.ndim}")

        # Update circular buffer for RMS calculation
        samples_to_add = len(mono_data)
        if samples_to_add >= self.rms_window_samples:
            # Replace entire buffer
            self.audio_buffer = mono_data[-self.rms_window_samples :]
            self.buffer_index = 0
        else:
            # Add to circular buffer
            end_index = self.buffer_index + samples_to_add
            if end_index <= self.rms_window_samples:
                self.audio_buffer[self.buffer_index : end_index] = mono_data
            else:
                # Wrap around
                first_part = self.rms_window_samples - self.buffer_index
                self.audio_buffer[self.buffer_index :] = mono_data[:first_part]
                self.audio_buffer[: end_index - self.rms_window_samples] = mono_data[
                    first_part:
                ]
            self.buffer_index = end_index % self.rms_window_samples

        # Calculate RMS
        rms = np.sqrt(np.mean(self.audio_buffer**2))
        rms_db = AudioConstants.AMPLITUDE_TO_DB_FACTOR * np.log10(
            max(rms, AudioConstants.NOISE_FLOOR)
        )

        # Calculate peak
        peak = np.max(np.abs(mono_data))
        peak_db = AudioConstants.AMPLITUDE_TO_DB_FACTOR * np.log10(
            max(peak, AudioConstants.NOISE_FLOOR)
        )

        # Update peak hold
        if peak_db > self.peak_hold_db:
            self.peak_hold_db = peak_db
            self.peak_hold_counter = self.peak_hold_samples
        else:
            self.peak_hold_counter -= samples_to_add
            if self.peak_hold_counter <= 0:
                self.peak_hold_db = peak_db

        # Increment frame counter
        self.frame_count += 1

        return rms_db, peak_db, self.peak_hold_db

    def reset(self) -> None:
        """Reset all level calculations."""
        self.audio_buffer.fill(0)
        self.buffer_index = 0
        self.peak_hold_db = AudioConstants.MIN_DB_LEVEL
        self.peak_hold_counter = 0
        self.frame_count = 0

    def get_frame_count(self) -> int:
        """Get current frame count."""
        return self.frame_count
