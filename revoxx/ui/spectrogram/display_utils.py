"""Utility functions for spectrogram display operations."""

import numpy as np
from typing import Optional
from ...constants import AudioConstants


def create_empty_spectrogram(
    n_mels: int, spec_frames: int, fill_value: float = AudioConstants.DB_MIN
) -> np.ndarray:
    """Create an empty spectrogram array with specified dimensions.

    Args:
        n_mels: Number of mel frequency bins
        spec_frames: Number of time frames
        fill_value: Value to fill the array with (default: minimum dB)

    Returns:
        numpy array of shape (n_mels, spec_frames) filled with fill_value
    """
    return np.ones((n_mels, spec_frames)) * fill_value


def needs_image_recreation(
    current_shape: Optional[tuple], target_n_mels: int, target_frames: int
) -> bool:
    """Check if spectrogram image needs to be recreated.

    Args:
        current_shape: Current shape of the image array (or None)
        target_n_mels: Target number of mel bins
        target_frames: Target number of frames

    Returns:
        True if recreation is needed, False otherwise
    """
    if current_shape is None:
        return True

    return current_shape[0] != target_n_mels or current_shape[1] != target_frames


def calculate_display_extent(spec_frames: int, n_mels: int) -> tuple:
    """Calculate extent for matplotlib imshow.

    Args:
        spec_frames: Number of spectrogram frames
        n_mels: Number of mel bins

    Returns:
        Tuple (x_min, x_max, y_min, y_max) for imshow extent
    """
    return (0, spec_frames - 1, 0, n_mels - 1)


def prepare_display_data(data: np.ndarray, target_shape: tuple) -> np.ndarray:
    """Prepare data for display, handling shape mismatches.

    Args:
        data: Input spectrogram data
        target_shape: Target shape (n_mels, spec_frames)

    Returns:
        Data reshaped/padded to match target shape
    """
    if data.shape == target_shape:
        return data

    target_mels, target_frames = target_shape
    current_mels, current_frames = data.shape

    # Create output array
    output = create_empty_spectrogram(target_mels, target_frames)

    # Copy available data
    min_mels = min(current_mels, target_mels)
    min_frames = min(current_frames, target_frames)
    output[:min_mels, :min_frames] = data[:min_mels, :min_frames]

    return output
