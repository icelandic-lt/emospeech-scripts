"""Frequency axis management for mel spectrograms."""

from typing import Optional, List, Tuple
import numpy as np
import librosa
from matplotlib.axes import Axes

from ..constants import UIConstants
from ..audio.processor import MelSpectrogramProcessor


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

    def update_default_axis(self, n_mels: int, fmin: float, fmax: float) -> None:
        """Update frequency axis with default settings.

        Args:
            n_mels: Number of mel bins
            fmin: Minimum frequency in Hz
            fmax: Maximum frequency in Hz
        """
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
        # Calculate adaptive parameters
        nyquist_freq = sample_rate / 2
        adaptive_fmax = nyquist_freq

        # Calculate adaptive mel bins
        freq_range = adaptive_fmax - fmin
        base_range = 24000 - 50  # Original range for 48kHz
        mel_scale_factor = freq_range / base_range
        adaptive_n_mels = max(80, int(96 * mel_scale_factor))

        # Update axis
        mel_freqs = self._get_mel_frequencies(adaptive_n_mels, fmin, adaptive_fmax)
        ticks, labels = self._calculate_ticks_and_labels(mel_freqs, adaptive_fmax)
        self._apply_ticks_and_labels(ticks, labels)
        self._reset_label_styles()

        return adaptive_n_mels, adaptive_fmax

    def highlight_max_frequency(self, max_freq: float, n_mels: int,
                              fmin: float, fmax: float) -> None:
        """Add or update orange highlight for maximum detected frequency.

        Args:
            max_freq: Maximum detected frequency in Hz
            n_mels: Number of mel bins
            fmin: Minimum frequency in Hz
            fmax: Maximum frequency in Hz
        """
        if max_freq <= 0:
            return

        # Get current axis state
        current_ticks = list(self.ax.get_yticks())
        current_labels = [label.get_text() for label in self.ax.get_yticklabels()]

        # Find mel bin for max frequency
        mel_freqs = self._get_mel_frequencies(n_mels, fmin, fmax)
        max_freq_bin = np.argmin(np.abs(mel_freqs - max_freq))

        # Check if we need to replace a nearby tick
        min_distance = n_mels / 20  # 5% separation
        replace_idx = None

        for i, tick in enumerate(current_ticks):
            if abs(tick - max_freq_bin) < min_distance:
                replace_idx = i
                break

        if 0 <= max_freq_bin < n_mels:
            if replace_idx is not None:
                # Replace nearby tick
                all_ticks = current_ticks.copy()
                all_ticks[replace_idx] = max_freq_bin
                all_labels = current_labels.copy()
                all_labels[replace_idx] = self._format_frequency(max_freq)
            else:
                # Add new tick
                all_ticks = sorted(current_ticks + [max_freq_bin])
                all_labels = []
                for tick in all_ticks:
                    if tick == max_freq_bin:
                        all_labels.append(self._format_frequency(max_freq))
                    else:
                        orig_idx = current_ticks.index(tick)
                        all_labels.append(current_labels[orig_idx])

            # Apply updates
            self.ax.set_yticks(all_ticks)
            self.ax.set_yticklabels(all_labels)

            # Color the max frequency label orange
            for i, (tick, label) in enumerate(zip(all_ticks, self.ax.get_yticklabels())):
                if (replace_idx is not None and i == replace_idx) or \
                   (replace_idx is None and tick == max_freq_bin):
                    label.set_color('orange')
                    label.set_weight('bold')

    def _get_mel_frequencies(self, n_mels: int, fmin: float, fmax: float) -> np.ndarray:
        """Get mel frequency values for each bin."""
        return librosa.mel_frequencies(
            n_mels=n_mels + 2,
            fmin=fmin,
            fmax=fmax
        )[1:-1]  # Remove edge bins

    def _calculate_ticks_and_labels(self, mel_freqs: np.ndarray,
                                   fmax: float) -> Tuple[np.ndarray, List[str]]:
        """Calculate tick positions and labels."""
        n_mels = len(mel_freqs)
        n_ticks = UIConstants.N_FREQUENCY_TICKS

        # Split ticks: more in lower frequencies
        lower_ticks = int(n_ticks * 0.6)
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

    def _format_frequency(self, freq: float) -> str:
        """Format frequency value for display."""
        if freq < 1000:
            return f'{int(freq)}'
        elif freq == int(freq / 1000) * 1000:  # Round kHz
            return f'{int(freq/1000)}k'
        else:
            return f'{freq/1000:.1f}k'

    def _apply_ticks_and_labels(self, ticks: np.ndarray, labels: List[str]) -> None:
        """Apply ticks and labels to axis."""
        self.ax.set_yticks(ticks)
        self.ax.set_yticklabels(labels)

    def _reset_label_styles(self) -> None:
        """Reset all labels to default color and weight."""
        for label in self.ax.get_yticklabels():
            label.set_color(UIConstants.COLOR_TEXT_INACTIVE)
            label.set_weight('normal')