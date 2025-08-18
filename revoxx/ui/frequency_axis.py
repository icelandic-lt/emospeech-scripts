"""Frequency axis management for mel spectrograms."""

from typing import List, Tuple
import numpy as np
import librosa
from matplotlib.axes import Axes

from ..constants import UIConstants
from ..audio.mel_factory import MelProcessorFactory


class FrequencyAxisManager:
    """Manages frequency axis display for mel spectrograms.

    Handles frequency tick calculation, label formatting, and special
    highlighting (e.g., maximum detected frequency in orange).
    """

    def __init__(self, ax: Axes):
        """Initialize frequency axis manager.

        Args:
            ax: Matplotlib axes to manage
        """
        self.ax = ax
        self._peak_indicator_position = None  # Track current peak indicator position
        self._base_ticks = []  # Store base frequency ticks
        self._base_labels = []  # Store base frequency labels

    def update_default_axis(self, n_mels: int, fmin: float, fmax: float) -> None:
        """Update frequency axis with default settings.

        Args:
            n_mels: Number of mel bins
            fmin: Minimum frequency in Hz
            fmax: Maximum frequency in Hz
        """
        # Reset peak indicator when updating axis
        self._peak_indicator_position = None

        mel_freqs = self._get_mel_frequencies(n_mels, fmin, fmax)
        ticks, labels = self._calculate_ticks_and_labels(mel_freqs, fmax)
        self._apply_ticks_and_labels(ticks, labels)
        self._reset_label_styles()

    def update_recording_axis(self, sample_rate: int, fmin: float) -> Tuple[int, float]:
        """Update frequency axis for a specific recording.

        Args:
            sample_rate: Recording sample rate in Hz
            fmin: Minimum frequency in Hz

        Returns:
            Tuple of (adaptive_n_mels, adaptive_fmax)
        """
        # Reset peak indicator when updating axis
        self._peak_indicator_position = None

        params = MelProcessorFactory.calculate_adaptive_params(sample_rate, fmin)
        adaptive_n_mels = params["n_mels"]
        adaptive_fmax = params["fmax"]

        # Update axis
        mel_freqs = self._get_mel_frequencies(adaptive_n_mels, fmin, adaptive_fmax)
        ticks, labels = self._calculate_ticks_and_labels(mel_freqs, adaptive_fmax)
        self._apply_ticks_and_labels(ticks, labels)
        self._reset_label_styles()

        return adaptive_n_mels, adaptive_fmax

    def highlight_max_frequency(
        self, max_freq: float, n_mels: int, fmin: float, fmax: float
    ) -> None:
        """Add or update orange highlight for maximum detected frequency.

        Args:
            max_freq: Maximum detected frequency in Hz
            n_mels: Number of mel bins
            fmin: Minimum frequency in Hz
            fmax: Maximum frequency in Hz
        """
        if max_freq <= 0 or not self._base_ticks:
            return

        # Find mel bin for max frequency
        mel_freqs = self._get_mel_frequencies(n_mels, fmin, fmax)
        max_freq_bin = np.argmin(np.abs(mel_freqs - max_freq))

        # Only update if peak position has changed significantly
        if (
            self._peak_indicator_position is not None
            and abs(max_freq_bin - self._peak_indicator_position) < 0.5
        ):
            return  # Peak hasn't moved enough to warrant update

        # Start with base ticks and labels
        all_ticks = self._base_ticks.copy()
        all_labels = self._base_labels.copy()

        # Check if we need to replace a nearby tick
        min_distance = n_mels / 20  # 5% separation
        replace_idx = None

        for i, tick in enumerate(all_ticks):
            if abs(tick - max_freq_bin) < min_distance:
                replace_idx = i
                break

        if 0 <= max_freq_bin < n_mels:
            if replace_idx is not None:
                # Replace nearby tick
                all_ticks[replace_idx] = max_freq_bin
                all_labels[replace_idx] = self._format_frequency(max_freq)
            else:
                # Add new tick at correct position
                insert_idx = 0
                for i, tick in enumerate(all_ticks):
                    if tick > max_freq_bin:
                        insert_idx = i
                        break
                else:
                    insert_idx = len(all_ticks)

                all_ticks.insert(insert_idx, max_freq_bin)
                all_labels.insert(insert_idx, self._format_frequency(max_freq))

            # Apply updates
            self.ax.set_yticks(all_ticks)
            self.ax.set_yticklabels(all_labels)

            # Store the new peak indicator position
            self._peak_indicator_position = max_freq_bin

            # Reset all labels to default style first
            for label in self.ax.get_yticklabels():
                label.set_color(UIConstants.COLOR_TEXT_INACTIVE)
                label.set_weight("normal")

            # Then highlight only the peak indicator
            for i, tick in enumerate(all_ticks):
                if tick == max_freq_bin:
                    self.ax.get_yticklabels()[i].set_color("orange")
                    self.ax.get_yticklabels()[i].set_weight("bold")
                    break

    @staticmethod
    def _get_mel_frequencies(n_mels: int, fmin: float, fmax: float) -> np.ndarray:
        """Get mel frequency values for each bin."""
        return librosa.mel_frequencies(n_mels=n_mels + 2, fmin=fmin, fmax=fmax)[
            1:-1
        ]  # Remove edge bins

    def _calculate_ticks_and_labels(
        self, mel_freqs: np.ndarray, fmax: float
    ) -> Tuple[np.ndarray, List[str]]:
        """Calculate tick positions and labels."""
        n_mels = len(mel_freqs)
        n_ticks = UIConstants.N_FREQUENCY_TICKS

        # Split ticks: more in lower frequencies
        lower_ticks = int(n_ticks * UIConstants.FREQ_TICKS_LOWER_FRACTION)
        upper_ticks = n_ticks - lower_ticks

        # Calculate indices
        lower_indices = np.linspace(0, n_mels // 3, lower_ticks, dtype=int)
        upper_indices = np.linspace(n_mels // 3 + 1, n_mels - 1, upper_ticks, dtype=int)

        log_indices = np.unique(np.concatenate([lower_indices, upper_indices]))
        log_indices[0] = 0
        log_indices[-1] = n_mels - 1

        # Create labels
        labels = []
        for i, idx in enumerate(log_indices):
            freq = mel_freqs[idx]
            # Show exact Nyquist for last tick
            if i == len(log_indices) - 1:
                freq = fmax
            labels.append(self._format_frequency(freq))

        return log_indices, labels

    @staticmethod
    def _format_frequency(freq: float) -> str:
        """Format frequency value for display."""
        if freq < 1000:
            return f"{int(freq)}"
        elif freq == int(freq / 1000) * 1000:  # Round kHz
            return f"{int(freq/1000)}k"
        else:
            return f"{freq/1000:.1f}k"

    def _apply_ticks_and_labels(self, ticks: np.ndarray, labels: List[str]) -> None:
        """Apply ticks and labels to axis."""
        # Store base ticks and labels for later use
        self._base_ticks = list(ticks)
        self._base_labels = list(labels)

        self.ax.set_yticks(ticks)
        self.ax.set_yticklabels(labels)

    def _reset_label_styles(self) -> None:
        """Reset all labels to default color and weight."""
        for label in self.ax.get_yticklabels():
            label.set_color(UIConstants.COLOR_TEXT_INACTIVE)
            label.set_weight("normal")
