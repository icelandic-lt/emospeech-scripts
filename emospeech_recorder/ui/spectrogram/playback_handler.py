"""Synchronized playback handler using shared state.

This module provides hardware-synchronized position updates from the
struct shared state.
"""

import sys
import tkinter as tk
from typing import Optional, TYPE_CHECKING
from matplotlib.lines import Line2D

from ...constants import UIConstants
from .controllers import PlaybackController, ZoomController

if TYPE_CHECKING:
    from ...audio.shared_state import SharedState


class PlaybackHandler:
    """Handles playback visualization synchronized with hardware timing.

    Instead of using time.time() for animation, this handler reads
    the current playback position from the shared audio state, ensuring
    accurate synchronization with the actual audio playback.
    """

    def __init__(self, parent_widget: tk.Widget, ax,
                 playback_controller: PlaybackController,
                 zoom_controller: ZoomController,
                 spec_frames: int,
                 shared_audio_state: 'SharedState'):
        """Initialize synchronized playback handler.

        Args:
            parent_widget: Parent tkinter widget for scheduling
            ax: Matplotlib axes for drawing
            playback_controller: Playback state controller
            zoom_controller: Zoom state controller
            spec_frames: Number of display frames
            shared_audio_state: Struct-based shared state for position info
        """
        self.parent = parent_widget
        self.ax = ax
        self.playback_controller = playback_controller
        self.zoom_controller = zoom_controller
        self.spec_frames = spec_frames
        self.shared_audio_state = shared_audio_state

        # Playback visualization
        self.playback_line: Optional[Line2D] = None
        self.animation_id: Optional[str] = None

        # Store total duration for calculations
        self.total_duration = 0.0
        self.sample_rate = 48000

        # Callbacks
        self.on_update_display = None
        self.on_update_time_axis = None
        self.on_draw_idle = None

    def start_playback(self, duration: float, recording_duration: float, sample_rate: int) -> None:
        """Start playback animation.

        Args:
            duration: Playback duration in seconds
            recording_duration: Total recording duration (for zoom calculations)
            sample_rate: Sample rate of the audio being played
        """

        # Clear any pending animation
        if self.animation_id:
            self.parent.after_cancel(self.animation_id)
            self.animation_id = None

        self.playback_controller.start(duration)
        self.playback_controller.recording_duration = recording_duration
        self.total_duration = duration
        self.sample_rate = sample_rate

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

        # Start animation with small delay to ensure player is ready
        self.parent.after(50, self._update_playback_position)

    def stop_playback(self) -> None:
        """Stop playback animation."""
        self.playback_controller.stop()
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
        """Update playback position from shared audio state."""
        # Check if still playing
        if not self.shared_audio_state:
            return

        playback_state = self.shared_audio_state.get_playback_state()
        status = playback_state.get('status', 0)

        # Check for invalid state first
        from ...audio.shared_state import SHARED_STATUS_INVALID, PLAYBACK_STATUS_PLAYING
        if status == SHARED_STATUS_INVALID:
            print("ERROR: Playback state not initialized", file=sys.stderr)
            self.stop_playback()
            return

        # If not playing, and we have a valid playback controller that thinks it's playing,
        # give it another chance (might be timing issue)
        if status != PLAYBACK_STATUS_PLAYING and self.playback_controller.is_playing:
            # Schedule another check in 20ms
            self.parent.after(20, self._update_playback_position)
            return
        elif status != PLAYBACK_STATUS_PLAYING:
            self.stop_playback()
            return

        # Get current position from shared state
        current_sample = playback_state.get('current_sample_position', 0)
        total_samples = playback_state.get('total_samples', 1)

        # Calculate position in seconds
        position_seconds = 0.0
        if total_samples > 0:
            position_seconds = current_sample / self.sample_rate

        # Check if finished
        # For FINISHING status, continue animating even if position hasn't updated
        from ...audio.shared_state import PLAYBACK_STATUS_FINISHING, PLAYBACK_STATUS_COMPLETED

        # Handle FINISHING status - override position to animate to end
        if status == PLAYBACK_STATUS_FINISHING:
            # For finishing, always use the exact total duration
            position_seconds = self.total_duration

        self.playback_controller.playback_position = position_seconds

        # Calculate animation parameters and update display
        if self.playback_controller.playback_duration > 0:
            x_pos, view_offset, visible_seconds = self.playback_controller.calculate_animation_phase(
                self.zoom_controller.zoom_level,
                self.spec_frames
            )

            self.zoom_controller.view_offset = view_offset
            self.playback_line.set_xdata([x_pos])
            if self.on_update_time_axis:
                self.on_update_time_axis(view_offset, view_offset + visible_seconds)

            # Update spectrogram if scrolling
            if view_offset > 0 and self.on_update_display:
                self.on_update_display()

            if self.on_draw_idle:
                self.on_draw_idle()

        # Handle continuing animation for FINISHING status
        if status == PLAYBACK_STATUS_FINISHING and position_seconds < self.total_duration:
            # Continue scheduling updates until we reach the end
            self._schedule_next_frame()
            return

        if current_sample >= total_samples - 1 or status == PLAYBACK_STATUS_COMPLETED:
            self.stop_playback()
        else:
            # Schedule next update
            self._schedule_next_frame()

    def _schedule_next_frame(self) -> None:
        """Schedule next animation frame."""
        if self.animation_id:
            try:
                self.parent.after_cancel(self.animation_id)
            except ValueError:
                pass

        # Update more frequently for smoother animation
        # Since we're reading from shared state, we can update faster
        update_interval = 10  # 10ms = 100 FPS

        self.animation_id = self.parent.after(
            update_interval,
            self._update_playback_position
        )