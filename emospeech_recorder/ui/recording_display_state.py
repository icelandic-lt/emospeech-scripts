"""State management for recording-specific display."""

from typing import Optional
from dataclasses import dataclass
from ..audio.processors import MelSpectrogramProcessor


@dataclass
class RecordingDisplayState:
    """Encapsulates recording-specific display state.

    Used when displaying saved recordings that may have different
    parameters than the current recording settings.
    """

    mel_processor: Optional[MelSpectrogramProcessor] = None
    n_mels: Optional[int] = None
    spec_frames: Optional[int] = None
    sample_rate: Optional[int] = None

    def clear(self) -> None:
        """Clear all recording-specific state."""
        self.mel_processor = None
        self.n_mels = None
        self.spec_frames = None
        self.sample_rate = None

    def is_active(self) -> bool:
        """Check if recording-specific display is active."""
        return self.mel_processor is not None
