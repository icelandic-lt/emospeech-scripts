"""Clipping visualization for spectrogram display."""

from typing import List, Optional
from matplotlib.axes import Axes
from matplotlib.text import Text
from ....constants import UIConstants


class ClippingVisualizer:
    """Manages clipping markers and warnings in the spectrogram display.

    This visualizer handles the display of vertical lines at clipping
    positions and shows a warning when clipping is detected.
    """

    def __init__(self, ax: Axes):
        """Initialize clipping visualizer.

        Args:
            ax: Matplotlib axes for drawing markers
        """
        self.ax = ax
        self.clipping_markers: List[int] = []
        self.clipping_warning: Optional[Text] = None

    def set_clipping_positions(self, positions: List[int]) -> None:
        """Set clipping marker positions.

        Args:
            positions: List of frame indices where clipping occurred
        """
        self.clipping_markers = positions

    def clear_markers(self) -> None:
        """Remove all clipping marker lines from display."""
        for line in self.ax.lines[:]:
            if hasattr(line, "_is_clipping_marker") and line._is_clipping_marker:
                line.remove()

    def add_marker_line(self, x_position: int) -> None:
        """Add a clipping marker line at the specified position.

        Args:
            x_position: X coordinate for the marker line
        """
        line = self.ax.axvline(
            x=x_position,
            color=UIConstants.COLOR_CLIPPING,
            linewidth=UIConstants.CLIPPING_LINE_WIDTH,
            alpha=UIConstants.CLIPPING_LINE_ALPHA,
        )
        line._is_clipping_marker = True

    def update_display(self, n_frames: int, spec_frames: int) -> None:
        """Updates display with all detected clipping positions and show warning if needed.

        Args:
            n_frames: Total number of frames in recording
            spec_frames: Number of display frames
        """
        self.clear_markers()

        # iterate over all clipping positions and map them to the scaled display position
        for clip_pos in self.clipping_markers:
            if 0 <= clip_pos < n_frames:
                # Map from recording frames to display frames
                display_pos = int((clip_pos / n_frames) * spec_frames)
                if 0 <= display_pos < spec_frames:
                    self.add_marker_line(display_pos)
        self.show_warning()

    def update_markers_for_zoom(
        self, start_frame: int, end_frame: int, spec_frames: int
    ) -> None:
        """Update clipping markers for zoomed view.

        Args:
            start_frame: First frame index of visible window
            end_frame: Last frame index of visible window
            spec_frames: Number of display frames
        """
        self.clear_markers()

        n_frames_visible = end_frame - start_frame
        if n_frames_visible > 0:
            for clip_pos in self.clipping_markers:
                if start_frame <= clip_pos < end_frame:
                    # Map to display position
                    relative_pos = (clip_pos - start_frame) / n_frames_visible
                    display_pos = int(relative_pos * spec_frames)
                    if 0 <= display_pos < spec_frames:
                        self.add_marker_line(display_pos)

    def update_markers_for_live(
        self,
        current_time: float,
        frame_count: int,
        spec_frames: int,
        frames_per_second: float,
        zoom_level: float,
    ) -> None:
        """Update clipping markers for live recording.

        Args:
            current_time: Current recording time in seconds
            frame_count: Total frames recorded
            spec_frames: Number of display frames
            frames_per_second: Frame rate
            zoom_level: Current zoom level
        """
        self.clear_markers()

        # For live recording, the spectrogram scrolls from right to left
        # New data appears on the right, old data scrolls off the left
        # We need to position markers based on how many frames ago they occurred

        for clip_pos in self.clipping_markers:
            # Calculate how many frames ago this clipping occurred
            frames_ago = frame_count - clip_pos

            if 0 <= frames_ago < spec_frames:
                # The marker should appear at position from the right
                # spec_frames - 1 is the rightmost (newest) position
                # 0 is the leftmost (oldest) position
                display_pos = spec_frames - 1 - frames_ago

                if 0 <= display_pos < spec_frames:
                    self.add_marker_line(display_pos)

    def show_warning(self) -> None:
        """Show or update clipping warning text."""
        if self.clipping_markers and not self.clipping_warning:
            self.clipping_warning = self.ax.text(
                UIConstants.CLIPPING_WARNING_POSITION[0],
                UIConstants.CLIPPING_WARNING_POSITION[1],
                UIConstants.CLIPPING_WARNING_SYMBOL,
                transform=self.ax.transAxes,
                color=UIConstants.COLOR_CLIPPING,
                fontsize=UIConstants.CLIPPING_WARNING_SIZE,
                fontweight="bold",
                ha="left",
                va="top",
            )
        elif not self.clipping_markers and self.clipping_warning:
            self.clipping_warning.remove()
            self.clipping_warning = None

    def clear(self) -> None:
        """Clear all clipping markers and warnings."""
        self.clear_markers()
        self.clipping_markers = []
        if self.clipping_warning:
            self.clipping_warning.remove()
            self.clipping_warning = None
