"""Zoom controller for spectrogram display."""

from typing import Tuple
from ....constants import UIConstants


class ZoomController:
    """Manages zoom state and calculations for spectrogram display.

    This controller handles zoom levels, view offsets, and calculations
    for visible time windows during zoom operations.
    """

    def __init__(self):
        """Initialize zoom controller with default zoom levels."""
        self.zoom_levels = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
        self.current_zoom_index = 0
        self.zoom_level = 1.0
        self.view_offset = 0.0
        self.recording_duration = 0.0

    def set_recording_duration(self, duration: float) -> None:
        """Set the duration of the current recording.

        Args:
            duration: Recording duration in seconds
        """
        self.recording_duration = duration

    def reset(self) -> None:
        """Reset zoom to default state (1x zoom, no offset)."""
        self.current_zoom_index = 0
        self.zoom_level = 1.0
        self.view_offset = 0.0

    def get_visible_seconds(self) -> float:
        """Calculate visible time window based on current zoom.

        Returns:
            Number of seconds visible at current zoom level
        """
        if self.recording_duration > 0:
            # For recordings: show proportional part of the full duration
            return self.recording_duration / self.zoom_level
        else:
            # For live recording: show standard window
            return UIConstants.SPECTROGRAM_DISPLAY_SECONDS / self.zoom_level

    def can_zoom_in(self) -> bool:
        """Check if zoom in is possible."""
        return self.current_zoom_index < len(self.zoom_levels) - 1

    def can_zoom_out(self) -> bool:
        """Check if zoom out is possible."""
        return self.current_zoom_index > 0

    def zoom_in(self) -> bool:
        """Zoom in one level.

        Returns:
            True if zoom was changed, False if already at max
        """
        if self.can_zoom_in():
            self.current_zoom_index += 1
            self.zoom_level = self.zoom_levels[self.current_zoom_index]
            return True
        return False

    def zoom_out(self) -> bool:
        """Zoom out one level.

        Returns:
            True if zoom was changed, False if already at min
        """
        if self.can_zoom_out():
            self.current_zoom_index -= 1
            self.zoom_level = self.zoom_levels[self.current_zoom_index]
            return True
        return False

    def calculate_zoom_offset(
        self,
        mouse_rel_x: float,
        old_visible_seconds: float,
        new_visible_seconds: float,
        time_at_mouse: float,
    ) -> float:
        """Calculate new view offset to keep time at mouse position stable.

        Args:
            mouse_rel_x: Relative mouse position (0-1)
            old_visible_seconds: Visible seconds before zoom
            new_visible_seconds: Visible seconds after zoom
            time_at_mouse: Time at mouse position before zoom

        Returns:
            New view offset in seconds
        """
        # Calculate new offset to keep time at mouse position stable
        new_offset = time_at_mouse - mouse_rel_x * new_visible_seconds

        # Ensure we stay within bounds
        max_duration = (
            self.recording_duration if self.recording_duration > 0 else float("inf")
        )
        if new_offset < 0:
            new_offset = 0
        elif new_offset + new_visible_seconds > max_duration:
            new_offset = max(0, max_duration - new_visible_seconds)

        return new_offset

    def apply_zoom_at_position(
        self, mouse_rel_x: float, zoom_in: bool, current_time: float = 0.0
    ) -> bool:
        """Apply zoom operation at mouse position.

        Args:
            mouse_rel_x: Relative mouse position (0-1)
            zoom_in: True to zoom in, False to zoom out
            current_time: Current time for live recording mode

        Returns:
            True if zoom was applied, False if at limit
        """
        # Get current state
        self.zoom_level
        old_visible_seconds = self.get_visible_seconds()

        # Calculate time at mouse position
        time_at_mouse = self.view_offset + mouse_rel_x * old_visible_seconds

        # Apply zoom
        if zoom_in and not self.can_zoom_in():
            return False
        if not zoom_in and not self.can_zoom_out():
            return False

        if zoom_in:
            self.zoom_in()
        else:
            self.zoom_out()

        # Calculate new view parameters
        new_visible_seconds = self.get_visible_seconds()

        # Update view offset to keep time at mouse stable
        self.view_offset = self.calculate_zoom_offset(
            mouse_rel_x, old_visible_seconds, new_visible_seconds, time_at_mouse
        )

        # Ensure we stay within bounds for live recording
        if self.recording_duration == 0 and current_time > 0:
            max_offset = max(0, current_time - new_visible_seconds)
            self.view_offset = min(self.view_offset, max_offset)

        return True

    def calculate_visible_frame_range(
        self,
        frames_per_second: float,
        display_seconds: float = UIConstants.SPECTROGRAM_DISPLAY_SECONDS,
    ) -> Tuple[int, int]:
        """Calculate the visible frame range based on current zoom and offset.

        Args:
            frames_per_second: Frame rate
            display_seconds: Display duration in seconds (default: SPECTROGRAM_DISPLAY_SECONDS)

        Returns:
            Tuple of (start_frame, visible_frame_count)
        """
        start_frame = int(self.view_offset * frames_per_second)
        visible_frames = int((display_seconds / self.zoom_level) * frames_per_second)
        return start_frame, visible_frames

    def get_zoom_info_text(self) -> str:
        """Get formatted zoom information text.

        Returns:
            Formatted string with zoom level and visible time
        """
        visible_seconds = self.get_visible_seconds()
        return f"Zoom: {self.zoom_level:.1f}x ({visible_seconds:.2f}s)"

    # --- Panning helpers ---
    def clamp_view_offset(
        self, desired_offset: float, current_time: float = 0.0
    ) -> float:
        """Clamp a desired view offset to valid bounds.

        Args:
            desired_offset: Proposed offset in seconds
            current_time: For live mode, the latest known time

        Returns:
            Clamped offset in seconds
        """
        visible_seconds = self.get_visible_seconds()

        if self.recording_duration > 0:
            max_offset = max(0.0, self.recording_duration - visible_seconds)
        else:
            # Live mode: clamp against current time (window must end <= current_time)
            max_offset = max(0.0, max(0.0, current_time) - visible_seconds)

        if desired_offset < 0.0:
            return 0.0
        if desired_offset > max_offset:
            return max_offset
        return desired_offset

    def pan_by_seconds(self, delta_seconds: float, current_time: float = 0.0) -> float:
        """Pan the view by a time delta, clamped to bounds.

        Args:
            delta_seconds: Positive pans to later times; negative pans to earlier times
            current_time: For live mode, the latest known time

        Returns:
            New clamped view_offset
        """
        desired = self.view_offset + delta_seconds
        self.view_offset = self.clamp_view_offset(desired, current_time=current_time)
        return self.view_offset
