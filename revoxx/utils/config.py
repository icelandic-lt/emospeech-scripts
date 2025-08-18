"""Configuration management for the Revoxx Recorder.

This module provides dataclass-based configuration management with
JSON serialization support. Configurations are organized hierarchically
for audio, display, and UI settings.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import json
from pathlib import Path

from ..constants import AudioConstants, UIConstants, FileConstants


@dataclass
class AudioConfig:
    """Audio configuration settings.

    Manages all audio-related configuration including device selection,
    format settings, and recording parameters.

    Attributes:
        sample_rate: Audio sample rate in Hz (default: 44100)
        channels: Number of channels (1=mono, 2=stereo)
        bit_depth: Bit depth (16 or 24)
        dtype: NumPy data type for audio arrays
        subtype: Soundfile subtype for saving
        input_device: Input device name or None for default
        output_device: Output device name or None for default
        sync_response_time_ms: Audio sync response time in milliseconds
    """

    sample_rate: int = AudioConstants.DEFAULT_SAMPLE_RATE
    channels: int = AudioConstants.DEFAULT_CHANNELS
    bit_depth: int = AudioConstants.DEFAULT_BIT_DEPTH
    dtype: str = "int16"
    subtype: str = FileConstants.PCM_16_SUBTYPE
    input_device: Optional[str] = None
    output_device: Optional[str] = None
    sync_response_time_ms: float = 10.0  # Default 10ms response time

    def __post_init__(self):
        """Set dtype and subtype based on bit depth.

        Automatically configures NumPy dtype and soundfile subtype
        based on the selected bit depth.
        """
        if self.bit_depth == 24:
            self.dtype = "int32"
            # For FLAC, subtype is None - format is determined by file extension
            self.subtype = (
                None
                if FileConstants.AUDIO_FILE_EXTENSION == ".flac"
                else FileConstants.PCM_24_SUBTYPE
            )
        else:
            self.dtype = "int16"
            # For FLAC, subtype is None - format is determined by file extension
            self.subtype = (
                None
                if FileConstants.AUDIO_FILE_EXTENSION == ".flac"
                else FileConstants.PCM_16_SUBTYPE
            )


@dataclass
class DisplayConfig:
    """Display configuration settings.

    Controls mel spectrogram visualization parameters.

    Attributes:
        show_spectrogram: Whether to display mel spectrogram
        display_seconds: Time window to display (seconds)
        n_mels: Number of mel frequency bins
        fmin: Minimum frequency in Hz
        fmax: Maximum frequency in Hz
    """

    show_spectrogram: bool = True
    display_seconds: float = UIConstants.SPECTROGRAM_DISPLAY_SECONDS
    n_mels: int = AudioConstants.N_MELS
    fmin: float = AudioConstants.FMIN
    fmax: float = AudioConstants.FMAX

    @property
    def frames_per_second(self) -> float:
        """Calculate frames per second for spectrogram display.

        Returns:
            float: Number of spectrogram frames per second

        Note:
            Currently uses default sample rate; should be linked
            to AudioConfig in future refactoring.
        """
        # This should use the sample rate from audio config
        # Will be linked when configs are combined
        return AudioConstants.DEFAULT_SAMPLE_RATE / AudioConstants.HOP_LENGTH


@dataclass
class UIConfig:
    """User interface configuration settings.

    Controls window appearance and behavior.

    Attributes:
        fullscreen: Start in fullscreen mode
        window_width: Window width (pixels or percentage if <= 100)
        window_height: Window height (pixels or percentage if <= 100)
        monitor: Monitor index for fullscreen (0-based)
        base_font_size: Base font size for text scaling
    """

    fullscreen: bool = False
    window_width: Optional[int] = None
    window_height: Optional[int] = None
    monitor: int = 0
    base_font_size: int = 60

    @property
    def is_window_size_percentage(self) -> tuple[bool, bool]:
        """Check if window dimensions are percentages (< 100).

        Returns:
            tuple[bool, bool]: (width_is_percentage, height_is_percentage)
        """
        width_is_pct = self.window_width is not None and self.window_width <= 100
        height_is_pct = self.window_height is not None and self.window_height <= 100
        return width_is_pct, height_is_pct


@dataclass
class RecorderConfig:
    """Main configuration container.

    Aggregates all configuration subsections and provides
    serialization/deserialization capabilities.

    Attributes:
        audio: Audio recording and playback settings
        display: Visualization settings
        ui: User interface settings
    """

    # Sub-configurations
    audio: AudioConfig = field(default_factory=AudioConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecorderConfig":
        """Create configuration from dictionary.

        Args:
            data: Dictionary with configuration data

        Returns:
            RecorderConfig: New configuration instance
        """
        return cls(
            audio=AudioConfig(**data.get("audio", {})),
            display=DisplayConfig(**data.get("display", {})),
            ui=UIConfig(**data.get("ui", {})),
        )

    def save(self, path: Path) -> None:
        """Save configuration to JSON file.

        Args:
            path: Output file path
        """
        data = {
            "audio": {
                "sample_rate": self.audio.sample_rate,
                "channels": self.audio.channels,
                "bit_depth": self.audio.bit_depth,
                "dtype": self.audio.dtype,
                "subtype": self.audio.subtype,
                "input_device": self.audio.input_device,
                "output_device": self.audio.output_device,
                "sync_response_time_ms": self.audio.sync_response_time_ms,
            },
            "display": {
                "show_spectrogram": self.display.show_spectrogram,
                "display_seconds": self.display.display_seconds,
                "n_mels": self.display.n_mels,
                "fmin": self.display.fmin,
                "fmax": self.display.fmax,
            },
            "ui": {
                "fullscreen": self.ui.fullscreen,
                "window_width": self.ui.window_width,
                "window_height": self.ui.window_height,
                "monitor": self.ui.monitor,
                "base_font_size": self.ui.base_font_size,
            },
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "RecorderConfig":
        """Load configuration from JSON file.

        Args:
            path: Configuration file path

        Returns:
            RecorderConfig: Loaded configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        with open(path, "r") as f:
            data = json.load(f)

        return cls.from_dict(data)


def load_config(config_path: Optional[Path] = None) -> RecorderConfig:
    """Load configuration from file or create default.

    Args:
        config_path: Optional path to configuration file

    Returns:
        RecorderConfig: Loaded or default configuration
    """
    if config_path and config_path.exists():
        return RecorderConfig.load(config_path)
    return RecorderConfig()


def save_config(config: RecorderConfig, config_path: Path) -> None:
    """Save configuration to file.

    Args:
        config: Configuration to save
        config_path: Output file path
    """
    config.save(config_path)
