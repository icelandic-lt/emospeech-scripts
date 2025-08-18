"""Playback controller for spectrogram animation."""

import time
from typing import Tuple
from ....constants import UIConstants


class PlaybackController:
    """Manages playback state and animation calculations.

    This controller handles the three-phase playback animation:
    1. Line moves from left to center
    2. Line stays at center while view scrolls
    3. Line moves from center to right
    """

    def __init__(self):
        """Initialize playback controller."""
        self.is_playing = False
        self.playback_position = 0.0
        self.playback_duration = 0.0
        self.playback_start_time = 0.0
        self.recording_duration = 0.0

    def start(self, duration: float) -> None:
        """Start playback with given duration.

        Args:
            duration: Total playback duration in seconds
        """
        self.is_playing = True
        self.playback_duration = duration
        self.playback_position = 0.0
        self.playback_start_time = time.time()

    def stop(self) -> None:
        """Stop playback."""
        self.is_playing = False
        self.playback_position = 0.0
        self.playback_duration = 0.0

    def update_position(self) -> float:
        """Update and return current playback position.

        Returns:
            Current playback position in seconds
        """
        if self.is_playing:
            actual_elapsed = time.time() - self.playback_start_time
            self.playback_position = actual_elapsed
        return self.playback_position

    def calculate_animation_phase(
        self, zoom_level: float, spec_frames: int
    ) -> Tuple[float, float, float]:
        """Calculate playback animation parameters.

        Args:
            zoom_level: Current zoom level
            spec_frames: Number of display frames

        Returns:
            Tuple of (x_position, view_offset, visible_seconds)
        """
        if self.playback_duration <= 0:
            return 0.0, 0.0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS

        # Calculate visible window based on recording duration and zoom
        visible_seconds = (
            self.recording_duration / zoom_level
            if self.recording_duration > 0
            else UIConstants.SPECTROGRAM_DISPLAY_SECONDS / zoom_level
        )

        # Special case: when zoomed out to show full recording (1x zoom)
        if visible_seconds >= self.playback_duration:
            # Simple left-to-right animation
            view_offset = 0.0
            x_pos_ratio = self.playback_position / self.playback_duration
            x_pos = x_pos_ratio * (spec_frames - 1)
        else:
            # Three-phase animation for zoomed views
            half_visible = visible_seconds / 2

            if self.playback_position < half_visible:
                # Phase 1: Line moves from left to center
                view_offset = 0.0
                x_pos_ratio = self.playback_position / visible_seconds
                x_pos = x_pos_ratio * (spec_frames - 1)

            elif self.playback_position < self.playback_duration - half_visible:
                # Phase 2: Line stays at center, view scrolls
                view_offset = self.playback_position - half_visible
                x_pos = (spec_frames - 1) * 0.5

            else:
                # Phase 3: Line moves from center to right
                view_offset = self.playback_duration - visible_seconds
                time_in_phase3 = self.playback_position - (
                    self.playback_duration - half_visible
                )
                x_pos_ratio = 0.5 + (time_in_phase3 / half_visible) * 0.5
                x_pos = x_pos_ratio * (spec_frames - 1)

        # Ensure x_pos is within bounds
        x_pos = min(x_pos, spec_frames - 1)

        return x_pos, view_offset, visible_seconds

    def is_finished(self) -> bool:
        """Check if playback has finished.

        Returns:
            True if playback position exceeds duration
        """
        return self.is_playing and self.playback_position >= self.playback_duration
