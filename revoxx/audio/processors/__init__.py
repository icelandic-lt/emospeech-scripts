"""Audio processors module.

This module provides audio processing components for the Revoxx Recorder.
"""

from .processor_base import AudioProcessor
from .clipping_detector import ClippingDetector
from .mel_spectrogram import MelSpectrogramProcessor

__all__ = ["AudioProcessor", "ClippingDetector", "MelSpectrogramProcessor"]
