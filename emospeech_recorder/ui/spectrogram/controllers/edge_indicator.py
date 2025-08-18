"""Edge indicator controller for spectrogram panning boundaries."""

from typing import Optional
from matplotlib.axes import Axes


class EdgeIndicator:
    """Manages visual edge indicators at left/right bounds of the spectrogram.

    Creates two vertical lines at the left and right display edges and provides
    methods to show them briefly when the user pans into a boundary.
    """

    def __init__(
        self,
        ax: Axes,
        *,
        color: str,
        linewidth: int,
        alpha: float,
        timeout_ms: int,
        after_call,
    ):
        """Initialize edge indicator controller.

        Args:
            ax: Matplotlib axes for drawing
            color: Line color
            linewidth: Line width in pixels
            alpha: Line alpha
            timeout_ms: Auto-hide timeout in milliseconds
            after_call: Callable like `tk.Widget.after` to schedule hide
        """
        self.ax = ax
        self.color = color
        self.linewidth = linewidth
        self.alpha = alpha
        self.timeout_ms = timeout_ms
        self._after = after_call

        self._left_line = None
        self._right_line = None
        self._hide_id: Optional[str] = None

    def ensure_created(self, spec_frames: int) -> None:
        """Create lines if missing and position to current width."""
        if self._left_line is None:
            self._left_line = self.ax.axvline(
                x=0,
                color=self.color,
                linewidth=self.linewidth,
                alpha=self.alpha,
                visible=False,
            )
        if self._right_line is None:
            self._right_line = self.ax.axvline(
                x=spec_frames - 1,
                color=self.color,
                linewidth=self.linewidth,
                alpha=self.alpha,
                visible=False,
            )
        else:
            # Update x if it already exists
            self._right_line.set_xdata([spec_frames - 1, spec_frames - 1])

    def update_positions(self, spec_frames: int) -> None:
        """Update x positions to match current display width."""
        if self._left_line is not None:
            self._left_line.set_xdata([0, 0])
        if self._right_line is not None:
            x = spec_frames - 1
            self._right_line.set_xdata([x, x])

    def show(self, side: str) -> None:
        """Show one of the edge indicators briefly.

        Args:
            side: 'left' or 'right'
        """
        if side == "left" and self._left_line is not None:
            self._left_line.set_visible(True)
        elif side == "right" and self._right_line is not None:
            self._right_line.set_visible(True)

        if self._hide_id is not None:
            try:
                # Cancel previous scheduled hide if any
                self._after.cancel(self._hide_id)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._hide_id = None

        # Schedule hide
        self._hide_id = self._after(self.timeout_ms, self.hide_all)

    def hide_all(self) -> None:
        """Hide both edge indicator lines."""
        if self._left_line is not None:
            self._left_line.set_visible(False)
        if self._right_line is not None:
            self._right_line.set_visible(False)
        self._hide_id = None
