"""Audio utility functions for common audio processing tasks."""

import numpy as np

from ..constants import AudioConstants


def normalize_audio(audio_data: np.ndarray, copy: bool = False) -> np.ndarray:
    """Normalize audio data to floating point range [-1, 1].

    Handles various audio formats:
    - int16: 16-bit PCM, normalized by 2^15
    - int32: 24-bit PCM in 32-bit container, normalized by 2^23
    - float32/float64: assumed already normalized

    Args:
        audio_data: Input audio data as numpy array
        copy: If True, always return a copy. If False, only copy when needed.

    Returns:
        Normalized audio data as float32 in range [-1, 1]

    Note:
        For multi-channel audio, normalization is applied to all channels.
    """
    if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
        # Already floating point, assume normalized
        if audio_data.dtype == np.float64 or copy:
            return audio_data.astype(np.float32, copy=True)
        return audio_data

    elif audio_data.dtype == np.int16:
        # 16-bit PCM
        return audio_data.astype(np.float32) / AudioConstants.NORM_FACTOR_16BIT

    elif audio_data.dtype == np.int32:
        # Most audio interfaces deliver 24-bit audio in 32-bit containers
        # The standard way is to use the full 32-bit range for normalization
        # This matches what soundfile does internally
        return audio_data.astype(np.float32) / AudioConstants.NORM_FACTOR_32BIT

    else:
        # Unknown format, try to convert to float32
        return audio_data.astype(np.float32)


def convert_to_mono(audio_data: np.ndarray) -> np.ndarray:
    """Convert multi-channel audio to mono.

    Args:
        audio_data: Audio data array, shape (samples,) for mono or (samples, channels) for multi-channel

    Returns:
        Mono audio data, shape (samples,)

    Note:
        For stereo, averages the channels. For multi-channel, takes the first channel.
    """
    if audio_data.ndim == 1:
        # Already mono
        return audio_data

    elif audio_data.ndim == 2:
        if audio_data.shape[1] == 1:
            # Single channel in 2D array
            return audio_data[:, 0]
        elif audio_data.shape[1] == 2:
            # Stereo - average the channels
            return np.mean(audio_data, axis=1)
        else:
            # Multi-channel - take first channel
            return audio_data[:, 0]

    else:
        raise ValueError(f"Unsupported audio shape: {audio_data.shape}")


def ensure_mono_normalized(audio_data: np.ndarray) -> np.ndarray:
    """Ensure audio is mono and normalized to [-1, 1].

    Convenience function that combines convert_to_mono and normalize_audio.

    Args:
        audio_data: Input audio data

    Returns:
        Mono, normalized audio as float32
    """
    audio_data = convert_to_mono(audio_data)
    return normalize_audio(audio_data)


def calculate_blocksize(response_time_ms: float, sample_rate: int) -> int:
    """Calculate audio blocksize from desired response time.

    Args:
        response_time_ms: Desired response time in milliseconds
        sample_rate: Sample rate in Hz

    Returns:
        Blocksize rounded to nearest power of 2
    """
    # Calculate ideal blocksize
    ideal_blocksize = int(sample_rate * response_time_ms / 1000)

    # Define limits
    MIN_BLOCKSIZE = 64  # Hardware minimum
    MAX_BLOCKSIZE = 4096  # Prevent excessive latency

    # Round to nearest power of 2
    blocksize = round_to_nearest_power_of_2(ideal_blocksize)

    # Apply limits
    return max(MIN_BLOCKSIZE, min(blocksize, MAX_BLOCKSIZE))


def round_to_nearest_power_of_2(n: int) -> int:
    """Round integer to nearest power of 2.

    Args:
        n: Integer to round

    Returns:
        Nearest power of 2
    """
    if n <= 0:
        return 1

    # Find the power of 2 on either side
    lower = 1 << (n - 1).bit_length() - 1
    upper = 1 << (n - 1).bit_length()

    # Return the closer one
    if n - lower < upper - n:
        return lower
    else:
        return upper


def db_to_linear(db: float) -> float:
    """Convert decibels to linear amplitude.

    Args:
        db: Value in decibels

    Returns:
        Linear amplitude (0.0 to 1.0)
    """
    return 10.0 ** (db / 20.0)


def linear_to_db(linear: float, ref: float = 1.0, min_db: float = -80.0) -> float:
    """Convert linear amplitude to decibels.

    Args:
        linear: Linear amplitude value
        ref: Reference value (default 1.0)
        min_db: Minimum dB value to return for very small inputs

    Returns:
        Value in decibels
    """
    if linear <= 0:
        return min_db

    db = 20.0 * np.log10(linear / ref)
    return max(db, min_db)


def rms(samples: np.ndarray) -> float:
    """Calculate RMS (Root Mean Square) of audio samples.

    Args:
        samples: Audio samples

    Returns:
        RMS value
    """
    return np.sqrt(np.mean(samples**2))


def peak(samples: np.ndarray) -> float:
    """Calculate peak (maximum absolute) value of audio samples.

    Args:
        samples: Audio samples

    Returns:
        Peak value
    """
    return np.max(np.abs(samples))
