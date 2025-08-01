"""Audio processing components."""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import numpy as np
import librosa

from ..constants import AudioConstants
from ..utils.audio_utils import normalize_audio


class AudioProcessor(ABC):
    """Base class for audio processors.

    Abstract base class defining the interface for audio processing
    components. All audio processors should inherit from this class
    and implement the process() method.

    Attributes:
        sample_rate: Audio sample rate in Hz
    """

    def __init__(self, sample_rate: int = AudioConstants.DEFAULT_SAMPLE_RATE):
        """Initialize the audio processor.

        Args:
            sample_rate: Sample rate in Hz (default: 44100)
        """
        self.sample_rate = sample_rate

    @abstractmethod
    def process(self, audio_data: np.ndarray) -> any:
        """Process audio data and return result.

        Args:
            audio_data: Input audio data as numpy array

        Returns:
            Processing result (type depends on specific processor)
        """
        pass


class ClippingDetector(AudioProcessor):
    """Detects clipping in audio signals.

    This processor analyzes audio data to detect clipping (signal saturation)
    which occurs when the audio level exceeds the maximum representable value.
    Clipping detection is useful for monitoring recording quality.

    Attributes:
        threshold: Normalized threshold for clipping detection (0.0 to 1.0)
    """

    def __init__(self,
                 sample_rate: int = AudioConstants.DEFAULT_SAMPLE_RATE,
                 threshold: float = AudioConstants.CLIPPING_THRESHOLD):
        """Initialize the clipping detector.

        Args:
            sample_rate: Audio sample rate in Hz
            threshold: Clipping threshold (0.95 = 95% of max level)
        """
        super().__init__(sample_rate)
        self.threshold = threshold

    def process(self, audio_data: np.ndarray) -> bool:
        """Check if audio data contains clipping.

        Args:
            audio_data: Audio samples (normalized or raw)

        Returns:
            bool: True if clipping is detected, False otherwise

        Note:
            Handles both normalized (-1 to 1) and raw audio data
        """
        # Use centralized normalization
        audio_norm = normalize_audio(audio_data)
        max_val = np.max(np.abs(audio_norm))
        return max_val >= self.threshold

    def find_clipping_positions(self, audio_data: np.ndarray,
                               hop_length: int = AudioConstants.HOP_LENGTH,
                               chunk_size: int = AudioConstants.AUDIO_CHUNK_SIZE) -> List[int]:
        """Find all clipping positions in audio data.

        Scans through audio in chunks to find positions where clipping occurs.
        Used for visual indication in spectrograms.

        Args:
            audio_data: Audio samples to analyze
            hop_length: Hop size for frame positioning
            chunk_size: Size of chunks to analyze

        Returns:
            List[int]: Frame positions where clipping is detected

        Note:
            Positions are spaced to avoid overlapping markers in visualization
        """
        clipping_positions = []

        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            if len(chunk) > 0 and self.process(chunk):
                frame_pos = i // hop_length

                # Avoid duplicate markers too close together
                if (not clipping_positions or
                    frame_pos - clipping_positions[-1] > AudioConstants.MIN_CLIPPING_MARKER_DISTANCE):
                    clipping_positions.append(frame_pos)

        return clipping_positions


class MelSpectrogramProcessor(AudioProcessor):
    """Processes audio to generate mel spectrograms.

    This processor converts audio signals to mel-scale spectrograms,
    which provide a perceptually-motivated frequency representation
    of audio. Mel spectrograms are commonly used for speech visualization
    and analysis.

    The mel scale approximates human auditory perception, with higher
    resolution at lower frequencies where speech information is concentrated.

    Attributes:
        n_fft: FFT window size
        hop_length: Number of samples between successive frames
        n_mels: Number of mel frequency bins
        fmin: Minimum frequency (Hz)
        fmax: Maximum frequency (Hz)
        mel_filter: Pre-computed mel filterbank matrix
    """

    def __init__(self,
                 sample_rate: int = AudioConstants.DEFAULT_SAMPLE_RATE,
                 n_fft: int = AudioConstants.N_FFT,
                 hop_length: int = AudioConstants.HOP_LENGTH,
                 n_mels: int = AudioConstants.N_MELS,
                 fmin: float = AudioConstants.FMIN,
                 fmax: float = AudioConstants.FMAX):
        """Initialize the mel spectrogram processor.

        Args:
            sample_rate: Audio sample rate in Hz
            n_fft: FFT window size (default: 2048)
            hop_length: Hop between frames (default: 512)
            n_mels: Number of mel bands (default: 80)
            fmin: Minimum frequency in Hz (default: 0)
            fmax: Maximum frequency in Hz (default: 8000)
        """
        super().__init__(sample_rate)
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.fmin = fmin
        self.fmax = fmax

        # Pre-compute mel filterbank for efficiency
        # Clamp fmax to Nyquist frequency if needed
        actual_fmax = min(fmax, sample_rate / 2)
        self.mel_filter = librosa.filters.mel(
            sr=sample_rate,
            n_fft=n_fft,
            n_mels=n_mels,
            fmin=fmin,
            fmax=actual_fmax
        )
        self.actual_fmax = actual_fmax

        # Pre-compute mel frequencies for efficiency
        self.mel_frequencies = librosa.mel_frequencies(
            n_mels=n_mels + 2,
            fmin=fmin,
            fmax=actual_fmax
        )[1:-1]  # Remove edge bins

    def process(self, audio_data: np.ndarray,
                normalization_factor: Optional[float] = None) -> Tuple[np.ndarray, Optional[float]]:
        """Convert audio frame to mel-scale dB values and detect highest frequency.

        Processes a single frame of audio data to produce mel-scale
        magnitude values in decibels.

        Args:
            audio_data: Audio frame (n_fft samples)
            normalization_factor: Optional factor to normalize raw audio.
                If None and data is not normalized, uses default 16-bit factor.

        Returns:
            Tuple of:
                - np.ndarray: Mel-scale magnitudes in dB (n_mels values)
                - float: Highest frequency with significant energy (Hz) or None

        Note:
            Automatically detects if input is already normalized (max <= 1.0)
            to handle both live recording and loaded audio files correctly.
        """
        # Use centralized normalization function
        audio_norm = normalize_audio(audio_data)

        # Apply window
        windowed = audio_norm * np.hanning(len(audio_norm))

        # Compute FFT
        fft = np.fft.rfft(windowed, n=self.n_fft)
        power = np.abs(fft) ** 2

        # Apply mel filterbank
        mel_power = np.dot(self.mel_filter, power[:self.n_fft // 2 + 1])

        # Convert to dB
        mel_db = 10 * np.log10(mel_power + AudioConstants.DB_REFERENCE)

        # Clamp to reasonable range - clip to 0 dB max (not DB_MAX which is for display)
        mel_db = np.clip(mel_db, AudioConstants.DB_MIN, 0)

        # Detect highest frequency with significant energy
        # Method 1: Use the raw FFT power spectrum for precise frequency detection
        power_db = 10 * np.log10(power[:self.n_fft // 2 + 1] + AudioConstants.DB_REFERENCE)

        # Find highest frequency above noise floor
        significant_bins = np.where(power_db > AudioConstants.FREQUENCY_NOISE_FLOOR_DB)[0]

        if len(significant_bins) > 0:
            highest_bin = significant_bins[-1]
            # Convert bin to frequency
            freq_per_bin = self.sample_rate / self.n_fft
            highest_freq = highest_bin * freq_per_bin
            # Clamp to Nyquist frequency (sample_rate / 2)
            highest_freq = min(highest_freq, self.sample_rate / 2)
        else:
            highest_freq = None

        # Method 2 (Alternative): Use mel bins for approximate detection
        # This is ~10x faster but less precise
        # Uncomment to use mel-based detection:
        # mel_threshold = -40  # dB threshold for mel bins
        # significant_mel_bins = np.where(mel_db > mel_threshold)[0]
        # if len(significant_mel_bins) > 0:
        #     highest_mel_bin = significant_mel_bins[-1]
        #     highest_freq = self.mel_frequencies[highest_mel_bin]
        # else:
        #     highest_freq = None

        return mel_db, highest_freq

    def process_file(self, audio_data: np.ndarray,
                     normalization_factor: Optional[float] = None) -> Tuple[np.ndarray, int]:
        """Process entire audio file to mel spectrogram frames.

        Converts a complete audio signal to a sequence of mel spectrogram
        frames using a sliding window approach.

        Args:
            audio_data: Complete audio signal
            normalization_factor: Optional normalization factor

        Returns:
            Tuple[np.ndarray, int]:
                - Mel spectrogram (n_mels x n_frames)
                - Number of frames processed

        Note:
            Returns transposed array for display (frequency bins as rows)
        """
        frames = []
        max_freq = 0.0

        for i in range(0, len(audio_data) - self.n_fft + 1, self.hop_length):
            frame = audio_data[i:i + self.n_fft]
            mel_db, highest_freq = self.process(frame, normalization_factor)
            frames.append(mel_db)
            if highest_freq and highest_freq > max_freq:
                max_freq = highest_freq

        result = np.array(frames).T
        return result, len(frames), max_freq  # Return transposed for display