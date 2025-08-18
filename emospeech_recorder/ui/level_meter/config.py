"""Configuration and standards for level meter."""

from enum import Enum
from dataclasses import dataclass
from typing import Dict


class RecordingStandard(Enum):
    """Recording standard presets."""

    BROADCAST_EBU = "broadcast_ebu"
    AUDIOBOOK_ACX = "audiobook_acx"
    PODCAST = "podcast"
    FILM_DIALOG = "film_dialog"
    MUSIC_VOCAL = "music_vocal"
    CUSTOM = "custom"


@dataclass
class LevelMeterConfig:
    """Configuration for level meter display.

    Attributes:
        target_min: Minimum target level in dBFS
        target_max: Maximum target level in dBFS
        warning_level: Warning level in dBFS (approaching clipping)
        danger_level: Danger level in dBFS (clipping imminent)
        rms_window_ms: RMS calculation window in milliseconds
        peak_hold_ms: Peak hold time in milliseconds
        show_rms: Show RMS level indicator
        show_peak: Show peak level indicator
        show_histogram: Show level histogram
        show_lufs: Show LUFS measurement (for broadcast)
        noise_floor_threshold: Noise floor threshold in dBFS
    """

    target_min: float = -18.0
    target_max: float = -12.0
    warning_level: float = -6.0
    danger_level: float = -3.0
    rms_window_ms: float = 300.0
    peak_hold_ms: float = 2000.0
    show_rms: bool = True
    show_peak: bool = True
    show_histogram: bool = False
    show_lufs: bool = False
    noise_floor_threshold: float = -60.0


# Preset configurations for different standards
RECORDING_STANDARDS: Dict[RecordingStandard, LevelMeterConfig] = {
    RecordingStandard.BROADCAST_EBU: LevelMeterConfig(
        target_min=-18.0,
        target_max=-12.0,
        warning_level=-9.0,
        danger_level=-6.0,
        show_lufs=True,
        rms_window_ms=400.0,
    ),
    RecordingStandard.AUDIOBOOK_ACX: LevelMeterConfig(
        target_min=-23.0,
        target_max=-18.0,
        warning_level=-6.0,
        danger_level=-3.0,
        noise_floor_threshold=-60.0,
        rms_window_ms=300.0,
    ),
    RecordingStandard.PODCAST: LevelMeterConfig(
        target_min=-16.0,
        target_max=-12.0,
        warning_level=-3.0,
        danger_level=-1.0,
        rms_window_ms=300.0,
    ),
    RecordingStandard.FILM_DIALOG: LevelMeterConfig(
        target_min=-27.0,
        target_max=-20.0,
        warning_level=-10.0,
        danger_level=-6.0,
        rms_window_ms=500.0,
    ),
    RecordingStandard.MUSIC_VOCAL: LevelMeterConfig(
        target_min=-18.0,
        target_max=-12.0,
        warning_level=-6.0,
        danger_level=-3.0,
        rms_window_ms=300.0,
        peak_hold_ms=3000.0,
    ),
}


def get_standard_description(standard: RecordingStandard) -> str:
    """Get human-readable description of recording standard.

    Args:
        standard: Recording standard enum

    Returns:
        Description string
    """
    descriptions = {
        RecordingStandard.BROADCAST_EBU: "EBU R128 broadcast standard (-23 LUFS integrated)",
        RecordingStandard.AUDIOBOOK_ACX: "ACX/Audible audiobook standard (RMS -23 to -18 dB)",
        RecordingStandard.PODCAST: "Podcast standard (-16 to -14 LUFS)",
        RecordingStandard.FILM_DIALOG: "Film dialog recording (-27 to -20 dBFS)",
        RecordingStandard.MUSIC_VOCAL: "Music vocal recording (-18 to -12 dBFS)",
        RecordingStandard.CUSTOM: "Custom user-defined levels",
    }
    return descriptions.get(standard, "Unknown standard")
