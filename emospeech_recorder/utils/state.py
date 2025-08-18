"""State management for Revoxx."""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
import threading


@dataclass
class RecordingState:
    """Manages the state of recordings.

    Thread-safe state management for recording sessions, tracking
    current utterance, recording status, and take numbers for each
    label. Supports browsing through different takes.

    Attributes:
        current_index: Index of current utterance in script
        is_recording: Whether currently recording
        is_playing: Whether currently playing audio
        takes: Mapping of label to highest take number
        displayed_takes: Which take is shown for each label
        labels: List of utterance labels from script
        utterances: List of utterance texts from script
    """

    # Current state
    current_index: int = 0
    is_recording: bool = False
    is_playing: bool = False

    # Takes management - label -> take number
    takes: Dict[str, int] = field(default_factory=dict)

    # Which take is currently displayed for each label
    displayed_takes: Dict[str, int] = field(default_factory=dict)

    # Script data
    labels: List[str] = field(default_factory=list)
    utterances: List[str] = field(default_factory=list)

    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get_current_take(self, label: str) -> int:
        """Get the take number to display for a given label.

        Args:
            label: Utterance label

        Returns:
            Take number to display (0 if no recordings)
        """
        with self._lock:
            return self.displayed_takes.get(label, self.takes.get(label, 0))

    def set_displayed_take(self, label: str, take: int) -> None:
        """Set which take to display for a label.

        Args:
            label: Utterance label
            take: Take number to display
        """
        with self._lock:
            self.displayed_takes[label] = take

    def increment_take(self, label: str) -> int:
        """Increment the take count for a label and return new value.

        Used when starting a new recording to get the next take number.

        Args:
            label: Utterance label

        Returns:
            New take number
        """
        with self._lock:
            self.takes[label] = self.takes.get(label, 0) + 1
            return self.takes[label]

    def get_take_count(self, label: str) -> int:
        """Get the current take count for a label.

        Args:
            label: Utterance label

        Returns:
            Number of takes recorded (0 if none)
        """
        with self._lock:
            return self.takes.get(label, 0)

    @property
    def current_label(self) -> Optional[str]:
        """Get the current label based on index.

        Returns:
            Current utterance label or None if index out of range
        """
        if 0 <= self.current_index < len(self.labels):
            return self.labels[self.current_index]
        return None

    @property
    def current_utterance(self) -> Optional[str]:
        """Get the current utterance based on index.

        Returns:
            Current utterance text or None if index out of range
        """
        if 0 <= self.current_index < len(self.utterances):
            return self.utterances[self.current_index]
        return None


@dataclass
class AudioState:
    """Manages audio processing state.

    Tracks audio device configuration and processing flags.

    Attributes:
        input_device_index: Selected input device index
        output_device_index: Selected output device index
        current_playback_take: Take number being played
        stop_playback_signal: Signal to stop playback
        audio_queue_active: Whether audio queue processing is active
    """

    # Audio device indices
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None

    # Playback state
    current_playback_take: int = 0
    stop_playback_signal: bool = False

    # Recording state
    audio_queue_active: bool = False


@dataclass
class UIState:
    """Manages UI state.

    Tracks window dimensions, visibility settings, and dynamically
    calculated font sizes.

    Attributes:
        window_width: Current window width in pixels
        window_height: Current window height in pixels
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        spectrogram_visible: Whether mel spectrogram is shown
        font_size_large: Large font size for main text
        font_size_medium: Medium font size for labels
        font_size_small: Small font size for status
        saved_window_geometry: Saved window geometry before fullscreen
    """

    # Window state
    window_width: int = 0
    window_height: int = 0
    screen_width: int = 0
    screen_height: int = 0

    # Spectrogram visibility
    spectrogram_visible: bool = True

    # Font sizes (calculated dynamically)
    font_size_large: int = 60
    font_size_medium: int = 42
    font_size_small: int = 30

    # Saved window position (geometry string)
    saved_window_geometry: Optional[str] = None

    def calculate_font_sizes(self, base_size: int, scale_factor: float) -> None:
        """Calculate font sizes based on window dimensions.

        Args:
            base_size: Base font size from configuration
            scale_factor: Scaling factor based on window size
        """
        from ..constants import UIConstants

        self.font_size_large = max(
            int(base_size * scale_factor), UIConstants.MIN_FONT_SIZE_LARGE
        )
        self.font_size_medium = max(
            int(self.font_size_large * UIConstants.FONT_SCALE_MEDIUM),
            UIConstants.MIN_FONT_SIZE_MEDIUM,
        )
        self.font_size_small = max(
            int(self.font_size_large * UIConstants.FONT_SCALE_SMALL),
            UIConstants.MIN_FONT_SIZE_SMALL,
        )


@dataclass
class AppState:
    """Main application state container.

    Central state management for the entire application, aggregating
    recording, audio, and UI state.

    Attributes:
        recording: Recording session state
        audio: Audio processing state
        ui: User interface state
    """

    recording: RecordingState = field(default_factory=RecordingState)
    audio: AudioState = field(default_factory=AudioState)
    ui: UIState = field(default_factory=UIState)

    def is_ready_to_play(self) -> bool:
        """Check if current utterance has recordings to play.

        Returns:
            True if the current utterance has at least one recording
        """
        current_label = self.recording.current_label
        if not current_label:
            return False
        return self.recording.get_take_count(current_label) > 0
