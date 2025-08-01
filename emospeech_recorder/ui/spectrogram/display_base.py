"""Base display functionality for spectrogram visualization."""

from typing import Optional, Tuple, List
import numpy as np
import tkinter as tk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.axes import Axes
from matplotlib.image import AxesImage
from scipy import interpolate

from ...constants import AudioConstants, UIConstants
from ...ui.frequency_axis import FrequencyAxisManager
from ...utils.config import AudioConfig, DisplayConfig


class SpectrogramDisplayBase:
    """Base class for spectrogram display functionality.

    Handles the core display operations including:
    - Figure and axes management
    - Canvas setup and resizing
    - Basic display updates
    - Frame resampling for display
    """

    def __init__(self, parent: tk.Widget, audio_config: AudioConfig,
                 display_config: DisplayConfig, shared_state: dict = None):
        """Initialize display base.

        Args:
            parent: Parent tkinter widget
            audio_config: Audio configuration
            display_config: Display configuration
            shared_state: Shared application state
        """
        self.parent = parent
        self.audio_config = audio_config
        self.display_config = display_config
        self.shared_state = shared_state or {}

        # Display components (initialized in subclass)
        self.fig: Optional[Figure] = None
        self.ax: Optional[Axes] = None
        self.im: Optional[AxesImage] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.canvas_widget: Optional[tk.Widget] = None
        self.freq_axis_manager: Optional[FrequencyAxisManager] = None

        # Display parameters
        self.frames_per_second = audio_config.sample_rate / AudioConstants.HOP_LENGTH
        self.spec_frames = int(UIConstants.SPECTROGRAM_DISPLAY_SECONDS * self.frames_per_second)
        self.time_per_frame = AudioConstants.HOP_LENGTH / audio_config.sample_rate

    def _init_display(self, figsize: Tuple[float, float] = None, dpi: int = None) -> None:
        """Initialize matplotlib display components.

        Args:
            figsize: Figure size in inches (width, height)
            dpi: Dots per inch for the figure
        """
        # Get parent widget size if not specified
        if figsize is None:
            self.parent.update_idletasks()
            parent_width = self.parent.winfo_width()
            parent_height = self.parent.winfo_height()

            dpi = dpi or UIConstants.SPECTROGRAM_DPI
            width_inches = max(6, (parent_width - 2) / dpi)  # Minimal padding
            height_inches = max(2, (parent_height - 2) / dpi)
            figsize = (width_inches, height_inches)

        # Create figure
        self.fig = Figure(
            figsize=figsize,
            dpi=dpi or UIConstants.SPECTROGRAM_DPI,
            facecolor=UIConstants.COLOR_BACKGROUND
        )

        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(UIConstants.COLOR_BACKGROUND)

        # Configure axes appearance
        self._configure_axes()

        # Initialize frequency axis manager
        self.freq_axis_manager = FrequencyAxisManager(self.ax)

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.parent)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)
        self.canvas_widget.config(
            bg=UIConstants.COLOR_BACKGROUND,
            highlightthickness=1,
            highlightbackground=UIConstants.COLOR_TEXT_INACTIVE
        )

        # Initial draw with adaptive layout
        self._apply_adaptive_layout()
        self.canvas.draw()

        # Bind resize event
        self.canvas_widget.bind('<Configure>', self._on_resize)

    def _configure_axes(self) -> None:
        """Configure axes appearance."""
        # Remove x-axis label to save vertical space
        self.ax.set_xlabel('', fontsize=UIConstants.AXIS_LABEL_FONTSIZE)
        self.ax.set_ylabel('Frequency (Hz)', color=UIConstants.COLOR_TEXT_INACTIVE,
                          fontsize=UIConstants.AXIS_LABEL_FONTSIZE)
        self.ax.tick_params(colors=UIConstants.COLOR_TEXT_INACTIVE,
                           labelsize=UIConstants.AXIS_TICK_FONTSIZE)

        # Add time label at right
        self.ax.text(1.01, 0, 'Time (s)',
                    transform=self.ax.transAxes,
                    color=UIConstants.COLOR_TEXT_INACTIVE,
                    fontsize=UIConstants.AXIS_LABEL_FONTSIZE,
                    verticalalignment='bottom',
                    horizontalalignment='left')

        # Remove top and right spines
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['bottom'].set_color(UIConstants.COLOR_TEXT_INACTIVE)
        self.ax.spines['left'].set_color(UIConstants.COLOR_TEXT_INACTIVE)

    def _on_resize(self, event) -> None:
        """Handle canvas resize events."""
        if event.width > 100 and event.height > 50:  # Ignore tiny sizes
            # Calculate new spec_frames based on window width
            # Keep the frames_per_second constant, adjust spec_frames for display seconds
            pixels_per_frame = 3  # Roughly 3 pixels per frame
            new_spec_frames = max(100, int(event.width / pixels_per_frame))

            # Update spec_frames if changed significantly
            if abs(self.spec_frames - new_spec_frames) > 10:
                old_spec_frames = self.spec_frames
                self.spec_frames = new_spec_frames

                # Notify subclasses of spec_frames change
                self._on_spec_frames_changed(old_spec_frames, new_spec_frames)

            # Calculate new DPI to fit the widget size
            target_width_inches = max(6, event.width / 100)
            new_dpi = event.width / target_width_inches

            # Limit DPI to reasonable range
            new_dpi = max(50, min(200, new_dpi))

            # Only update if DPI changed significantly
            if abs(self.fig.dpi - new_dpi) > 5:
                self.fig.set_dpi(new_dpi)
                self._apply_adaptive_layout()
                self.canvas.draw_idle()

    def _apply_adaptive_layout(self) -> None:
        """Apply simple, consistent layout."""
        # Use fixed margins that work well
        self.fig.tight_layout(rect=[0, 0, 0.98, 1])

    def _on_spec_frames_changed(self, old_frames: int, new_frames: int) -> None:
        """Called when spec_frames changes due to resize.

        Args:
            old_frames: Previous number of frames
            new_frames: New number of frames
        """
        # To be overridden by subclasses if needed
        pass

    def _update_time_axis(self, start_time: float, end_time: float) -> None:
        """Update time axis labels.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
        """
        # Update x-axis to show time range
        xticks = np.linspace(0, self.spec_frames - 1, num=5)
        xlabels = [f'{np.linspace(start_time, end_time, num=5)[i]:.1f}'
                   for i in range(5)]
        self.ax.set_xticks(xticks)
        self.ax.set_xticklabels(xlabels)

    def _resample_frames_to_display(self, visible_array: np.ndarray,
                                   n_mels: int, n_frames_visible: int) -> np.ndarray:
        """Resample frames to match display width.

        Args:
            visible_array: Array of visible frames
            n_mels: Number of mel bins
            n_frames_visible: Number of visible frames

        Returns:
            Resampled array matching display width
        """
        # Create interpolation grid
        x_old = np.linspace(0, 1, n_frames_visible)
        x_new = np.linspace(0, 1, self.spec_frames)

        # Interpolate each mel bin
        resampled = np.zeros((n_mels, self.spec_frames))
        for i in range(n_mels):
            f = interpolate.interp1d(x_old, visible_array[i, :],
                                   kind='linear', fill_value='extrapolate')
            resampled[i, :] = f(x_new)

        return resampled

    def update_display_data(self, data: np.ndarray, extent: List[float] = None) -> None:
        """Update the displayed spectrogram data.

        Args:
            data: 2D array of spectrogram data
            extent: Display extent [left, right, bottom, top]
        """
        if self.im is not None:
            self.im.set_data(data)
            self.im.set_clim(vmin=AudioConstants.DB_MIN, vmax=AudioConstants.DB_MAX)

            if extent:
                self.im.set_extent(extent)

    def clear_display(self) -> None:
        """Clear the display."""
        if self.im is not None:
            # Reset to empty data
            empty_data = np.ones((self.ax.get_ylim()[1], self.spec_frames)) * AudioConstants.DB_MIN
            self.update_display_data(empty_data)

    def draw_idle(self) -> None:
        """Request a redraw when idle."""
        if self.canvas:
            self.canvas.draw_idle()