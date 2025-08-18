"""Base class for audio processors."""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic
import numpy as np

from ...constants import AudioConstants

# Type variable for processor output
T = TypeVar("T")


class AudioProcessor(ABC, Generic[T]):
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
            sample_rate: Sample rate in Hz (default: 48000)
        """
        self.sample_rate = sample_rate

    @abstractmethod
    def process(self, audio_data: np.ndarray) -> T:
        """Process audio data and return result.

        Args:
            audio_data: Input audio data as numpy array

        Returns:
            Processing result (type depends on specific processor)
        """
