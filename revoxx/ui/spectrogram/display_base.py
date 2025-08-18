"""Base display functionality for spectrogram visualization."""

from typing import Optional, Tuple
import numpy as np
import tkinter as tk

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

    # Display constants
    MIN_DPI = 50  # Minimum DPI for display
    MAX_DPI = 200  # Maximum DPI for display
    MIN_CANVAS_WIDTH = 100  # Minimum canvas width in pixels
    MIN_CANVAS_HEIGHT = 50  # Minimum canvas height in pixels
    PIXELS_PER_FRAME = 3  # Approximate pixels per spectrogram frame
    MIN_SPEC_FRAMES = 100  # Minimum number of spectrogram frames
    MARGIN_SCALE_FACTOR = 0.006  # Scale factor for adaptive margin calculation

    def __init__(
        self,
        parent: tk.Widget,
        audio_config: AudioConfig,
        display_config: DisplayConfig,
        manager_dict: dict = None,
    ):
        """Initialize display base.

        Args:
            parent: Parent tkinter widget
            audio_config: Audio configuration
            display_config: Display configuration
            manager_dict: Shared manager dictionary
        """
        self.parent = parent
        self.audio_config = audio_config
        self.display_config = display_config
        self.manager_dict = manager_dict or {}

        # Display components (initialized in subclass)
        self.fig: Optional[Figure] = None
        self.ax: Optional[Axes] = None
        self.im: Optional[AxesImage] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.canvas_widget: Optional[tk.Widget] = None
        self.freq_axis_manager: Optional[FrequencyAxisManager] = None

        # Display parameters
        self.frames_per_second = audio_config.sample_rate / AudioConstants.HOP_LENGTH
        self.spec_frames = int(
            UIConstants.SPECTROGRAM_DISPLAY_SECONDS * self.frames_per_second
        )
        self.time_per_frame = AudioConstants.HOP_LENGTH / audio_config.sample_rate

    def _init_display(
        self, figsize: Tuple[float, float] = None, dpi: int = None
    ) -> None:
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

            width_inches, height_inches, calculated_dpi = (
                self._calculate_figure_dimensions(parent_width - 2, parent_height - 2)
            )
            figsize = (width_inches, height_inches)
            dpi = dpi or calculated_dpi

        # Create figure
        self.fig = Figure(
            figsize=figsize,
            dpi=dpi or UIConstants.SPECTROGRAM_DPI,
            facecolor=UIConstants.COLOR_BACKGROUND,
            constrained_layout=False,
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
            highlightbackground=UIConstants.COLOR_TEXT_INACTIVE,
        )

        # Initial draw with adaptive layout
        self._apply_adaptive_layout()
        self.canvas.draw()

        # Bind resize event
        self.canvas_widget.bind("<Configure>", self._on_resize)

    def _configure_axes(self) -> None:
        """Configure axes appearance."""
        # Not setting x-axis label to save vertical space
        self.ax.set_ylabel(
            "Frequency (Hz)",
            color=UIConstants.COLOR_TEXT_INACTIVE,
            fontsize=UIConstants.AXIS_LABEL_FONTSIZE,
        )
        self.ax.tick_params(
            colors=UIConstants.COLOR_TEXT_INACTIVE,
            labelsize=UIConstants.AXIS_TICK_FONTSIZE,
        )

        # Remove top and right spines
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["bottom"].set_color(UIConstants.COLOR_TEXT_INACTIVE)
        self.ax.spines["left"].set_color(UIConstants.COLOR_TEXT_INACTIVE)

    def _calculate_figure_dimensions(
        self, width_pixels: int, height_pixels: int
    ) -> Tuple[float, float, int]:
        """Calculate optimal figure dimensions for given pixel size.

        Args:
            width_pixels: Available width in pixels
            height_pixels: Available height in pixels

        Returns:
            Tuple of (width_inches, height_inches, dpi)
        """
        # Calculate DPI to fit the widget size
        target_width_inches = max(
            UIConstants.ADAPTIVE_MARGIN_MIN_WIDTH_INCHES, width_pixels / 100
        )
        dpi = width_pixels / target_width_inches

        # Limit DPI to reasonable range
        dpi = max(self.MIN_DPI, min(self.MAX_DPI, dpi))

        # Calculate figure size in inches
        width_inches = width_pixels / dpi
        height_inches = height_pixels / dpi

        return width_inches, height_inches, int(dpi)

    def _update_figure_size(self, width_pixels: int, height_pixels: int) -> bool:
        """Update matplotlib figure size to match canvas size.

        Args:
            width_pixels: Canvas width in pixels
            height_pixels: Canvas height in pixels

        Returns:
            True if figure was resized, False otherwise
        """
        width_inches, height_inches, new_dpi = self._calculate_figure_dimensions(
            width_pixels, height_pixels
        )

        # Check if we need to update
        current_size = self.fig.get_size_inches()
        size_changed = (
            abs(current_size[0] - width_inches)
            > UIConstants.FIGURE_SIZE_CHANGE_THRESHOLD
            or abs(current_size[1] - height_inches)
            > UIConstants.FIGURE_SIZE_CHANGE_THRESHOLD
        )
        dpi_changed = abs(self.fig.dpi - new_dpi) > UIConstants.DPI_CHANGE_THRESHOLD

        if size_changed or dpi_changed:
            # Update figure size
            self.fig.set_size_inches(width_inches, height_inches, forward=False)

            # Update DPI if changed
            if dpi_changed:
                self.fig.set_dpi(new_dpi)

            # Apply layout and redraw
            self._apply_adaptive_layout()
            return True

        return False

    def _on_resize(self, event) -> None:
        """Handle canvas resize events."""
        if (
            event.width > self.MIN_CANVAS_WIDTH
            and event.height > self.MIN_CANVAS_HEIGHT
        ):  # Ignore tiny sizes
            # Force the canvas widget to use the full available size
            self.canvas_widget.configure(width=event.width, height=event.height)

            # Force matplotlib to resize its internal canvas
            self.canvas.resize(event)

            # First update figure size to match canvas
            figure_resized = self._update_figure_size(event.width, event.height)

            # Calculate new spec_frames based on window width
            # Keep the frames_per_second constant, adjust spec_frames for display seconds
            pixels_per_frame = self.PIXELS_PER_FRAME
            new_spec_frames = max(
                self.MIN_SPEC_FRAMES, int(event.width / pixels_per_frame)
            )

            if self.spec_frames != new_spec_frames:
                old_spec_frames = self.spec_frames
                self.spec_frames = new_spec_frames

                # Notify subclasses of spec_frames change
                self._on_spec_frames_changed(old_spec_frames, new_spec_frames)
            elif figure_resized:
                # Figure was resized but spec_frames stayed the same
                self._on_figure_size_changed()

    def _apply_adaptive_layout(self) -> None:
        """Apply simple, consistent layout."""
        # Calculate adaptive left margin based on figure width
        # For narrow windows, we need more space for the y-axis labels
        fig_width_inches = self.fig.get_figwidth()

        # Scale left margin: more space for narrow windows, less for wide windows
        # At 6 inches wide: 10% margin, at 16 inches wide: 4% margin
        if fig_width_inches <= UIConstants.ADAPTIVE_MARGIN_MIN_WIDTH_INCHES:
            left_margin = UIConstants.ADAPTIVE_MARGIN_MAX
        elif fig_width_inches >= UIConstants.ADAPTIVE_MARGIN_MAX_WIDTH_INCHES:
            left_margin = UIConstants.ADAPTIVE_MARGIN_MIN
        else:
            # Linear interpolation between min and max width
            width_range = (
                UIConstants.ADAPTIVE_MARGIN_MAX_WIDTH_INCHES
                - UIConstants.ADAPTIVE_MARGIN_MIN_WIDTH_INCHES
            )
            margin_range = (
                UIConstants.ADAPTIVE_MARGIN_MAX - UIConstants.ADAPTIVE_MARGIN_MIN
            )
            left_margin = UIConstants.ADAPTIVE_MARGIN_MAX - (
                (fig_width_inches - UIConstants.ADAPTIVE_MARGIN_MIN_WIDTH_INCHES)
                / width_range
                * margin_range
            )

        # Use subplots_adjust to control margins precisely
        self.fig.subplots_adjust(
            left=left_margin,
            right=UIConstants.SUBPLOT_MARGIN_RIGHT,
            top=UIConstants.SUBPLOT_MARGIN_TOP,
            bottom=UIConstants.SUBPLOT_MARGIN_BOTTOM,
        )

    def _on_spec_frames_changed(self, old_frames: int, new_frames: int) -> None:
        """Called when spec_frames changes due to resize.

        Args:
            old_frames: Previous number of frames
            new_frames: New number of frames
        """
        # Hook method for subclasses to respond to spec_frames changes

    def _on_figure_size_changed(self) -> None:
        """Called when figure size changes but spec_frames stays the same.

        This method is called during resize when the figure dimensions change
        but spec_frames doesn't change significantly. Subclasses can override
        this to update their display accordingly.
        """
        # Hook method for subclasses to respond to figure size changes

    def _update_time_axis_labels(self, start_time: float, end_time: float) -> None:
        """Update time axis labels.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
        """
        # Update x-axis to show time range
        num_ticks = 5  # Number of time axis ticks
        xticks = np.linspace(0, self.spec_frames - 1, num=num_ticks)
        xlabels = [
            f"{np.linspace(start_time, end_time, num=num_ticks)[i]:.2f}"
            for i in range(num_ticks)
        ]
        self.ax.set_xticks(xticks)
        self.ax.set_xticklabels(xlabels)

    def _resample_frames_to_display(
        self, visible_array: np.ndarray, n_mels: int, n_frames_visible: int
    ) -> np.ndarray:
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
            f = interpolate.interp1d(
                x_old, visible_array[i, :], kind="linear", fill_value="extrapolate"
            )
            resampled[i, :] = f(x_new)

        return resampled

    def update_display_data(self, data: np.ndarray, n_mels: int) -> None:
        """Update the displayed spectrogram data.

        Args:
            data: 2D array of spectrogram data
            n_mels: Number of mel bins for extent calculation
        """
        if self.im is not None:
            self.im.set_data(data)
            self.im.set_clim(vmin=AudioConstants.DB_MIN, vmax=AudioConstants.DB_MAX)

            # Always set extent based on current dimensions
            extent = (0, self.spec_frames - 1, 0, n_mels - 1)
            self.im.set_extent(extent)

    def clear_display(self) -> None:
        """Clear the display."""
        if self.im is not None:
            # Reset to empty data
            # Get number of mel bins from y-axis limits (ylim goes from 0 to n_mels-1)
            n_mels = int(self.ax.get_ylim()[1] + 1)
            empty_data = np.ones((n_mels, self.spec_frames)) * AudioConstants.DB_MIN
            self.update_display_data(empty_data, n_mels)

    def draw_idle(self) -> None:
        """Request a redraw when idle."""
        if self.canvas:
            self.canvas.draw_idle()
