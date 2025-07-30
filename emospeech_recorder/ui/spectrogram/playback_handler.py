"""Handler for playback functionality."""

from typing import Optional
import tkinter as tk
from matplotlib.lines import Line2D

from ...constants import UIConstants
from .controllers import PlaybackController, ZoomController


class PlaybackHandler:
    """Handles playback visualization for the spectrogram display.

    Manages:
    - Playback line animation
    - View scrolling during playback
    - Animation timing
    """

    def __init__(self, parent_widget: tk.Widget, ax,
                 playback_controller: PlaybackController,
                 zoom_controller: ZoomController,
                 spec_frames: int):
        """Initialize playback handler.

        Args:
            parent_widget: Parent tkinter widget for scheduling
            ax: Matplotlib axes for drawing
            playback_controller: Playback state controller
            zoom_controller: Zoom state controller
            spec_frames: Number of display frames
        """
        self.parent = parent_widget
        self.ax = ax
        self.playback_controller = playback_controller
        self.zoom_controller = zoom_controller
        self.spec_frames = spec_frames

        # Playback visualization
        self.playback_line: Optional[Line2D] = None
        self.animation_id: Optional[int] = None

        # Callbacks
        self.on_update_display = None
        self.on_update_time_axis = None
        self.on_draw_idle = None

    def start_playback(self, duration: float, recording_duration: float = 0) -> None:
        """Start playback animation.

        Args:
            duration: Playback duration in seconds
            recording_duration: Total recording duration (for zoom calculations)
        """
        # Clear any pending animation
        if self.animation_id:
            self.parent.after_cancel(self.animation_id)
            self.animation_id = None

        self.playback_controller.start(duration)
        self.playback_controller.recording_duration = recording_duration

        # Reset view offset for playback
        self.zoom_controller.view_offset = 0.0

        # Update time axis for current zoom
        if recording_duration > 0:
            visible_seconds = recording_duration / self.zoom_controller.zoom_level
        else:
            visible_seconds = UIConstants.SPECTROGRAM_DISPLAY_SECONDS / self.zoom_controller.zoom_level

        if self.on_update_time_axis:
            self.on_update_time_axis(0, visible_seconds)

        # Update spectrogram view if zoomed
        if self.zoom_controller.zoom_level > 1.0 and self.on_update_display:
            self.on_update_display()

        # Create playback line if needed
        if self.playback_line is None:
            self.playback_line = self.ax.axvline(
                x=0,
                color=UIConstants.COLOR_PLAYBACK_LINE,
                linewidth=UIConstants.PLAYBACK_LINE_WIDTH
            )
        else:
            self.playback_line.set_xdata([0])
            self.playback_line.set_visible(True)

        # Start animation
        self._update_playback_position()

    def stop_playback(self) -> None:
        """Stop playback animation."""
        self.playback_controller.stop()

        # Cancel animation
        if self.animation_id:
            try:
                self.parent.after_cancel(self.animation_id)
            except ValueError:
                pass
            self.animation_id = None

        # Hide playback line
        if self.playback_line:
            self.playback_line.set_visible(False)

        if self.on_draw_idle:
            self.on_draw_idle()

    def _update_playback_position(self) -> None:
        """Update playback position indicator."""
        if not self.playback_controller.is_playing:
            return

        # Update position
        self.playback_controller.update_position()

        if self.playback_controller.playback_duration > 0:
            # Get animation parameters
            x_pos, view_offset, visible_seconds = self.playback_controller.calculate_animation_phase(
                self.zoom_controller.zoom_level,
                self.spec_frames
            )

            # Update zoom controller's view offset
            self.zoom_controller.view_offset = view_offset

            # Update playback line position
            self.playback_line.set_xdata([x_pos])

            # Update time axis
            if self.on_update_time_axis:
                self.on_update_time_axis(view_offset, view_offset + visible_seconds)

            # Update spectrogram if scrolling
            if view_offset > 0 and self.on_update_display:
                self.on_update_display()

            if self.on_draw_idle:
                self.on_draw_idle()

        # Continue animation
        if self.playback_controller.is_finished():
            self.stop_playback()
        else:
            self._schedule_next_frame()

    def _schedule_next_frame(self) -> None:
        """Schedule next animation frame."""
        if self.animation_id:
            try:
                self.parent.after_cancel(self.animation_id)
            except ValueError:
                pass

        self.animation_id = self.parent.after(
            UIConstants.ANIMATION_UPDATE_MS,
            self._update_playback_position
        )