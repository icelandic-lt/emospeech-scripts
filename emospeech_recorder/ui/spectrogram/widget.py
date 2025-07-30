"""Main mel spectrogram widget that coordinates all components."""

from typing import Optional, List, Tuple
import numpy as np
import tkinter as tk
import queue

from ...constants import AudioConstants, UIConstants
from ...audio.processor import MelSpectrogramProcessor, ClippingDetector
from ...audio.mel_factory import MelProcessorFactory
from ...utils.config import AudioConfig, DisplayConfig
from ..recording_display_state import RecordingDisplayState

from .display_base import SpectrogramDisplayBase
from .recording_handler import RecordingHandler
from .playback_handler import PlaybackHandler
from .recording_display import RecordingDisplay
from .controllers import ZoomController, PlaybackController, ClippingVisualizer


class MelSpectrogramWidget(SpectrogramDisplayBase):
    """Real-time mel spectrogram display widget with recording and playback.

    This widget provides a complete mel spectrogram visualization system
    combining live recording, playback animation, and zoom functionality.

    Constants:
        ZOOM_LEVELS: Available zoom levels
        BASE_FREQ_RANGE: Original frequency range for mel scaling
        MIN_ADAPTIVE_MELS: Minimum number of mel bins
        BASE_MEL_BINS: Base number of mel bins for scaling
        ZOOM_INDICATOR_HIDE_DELAY_MS: Auto-hide delay for zoom indicator
        ZOOM_INDICATOR_FONTSIZE: Font size for zoom indicator
        FIGURE_PADDING: Padding for figure size calculation
    """

    # Constants for frequently used calculations
    ZOOM_LEVELS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
    BASE_FREQ_RANGE = 24000 - 50
    MIN_ADAPTIVE_MELS = 80
    BASE_MEL_BINS = 96
    ZOOM_INDICATOR_HIDE_DELAY_MS = 2000
    ZOOM_INDICATOR_FONTSIZE = 10
    FIGURE_PADDING = 20

    def __init__(self, parent: tk.Widget, audio_config: AudioConfig,
                 display_config: DisplayConfig, shared_state: dict = None):
        """Initialize the mel spectrogram widget.

        Args:
            parent: Parent tkinter widget
            audio_config: Audio configuration
            display_config: Display configuration
            shared_state: Shared application state
        """
        super().__init__(parent, audio_config, display_config, shared_state)

        # Initialize mel processor
        self.mel_processor, self.adaptive_n_mels = MelProcessorFactory.create_for_sample_rate(
            audio_config.sample_rate,
            display_config.fmin
        )

        # Print adaptive settings
        params = MelProcessorFactory.calculate_adaptive_params(
            audio_config.sample_rate,
            display_config.fmin
        )
        print(f"Mel spectrogram frequency range:")
        print(f"  Sample rate: {audio_config.sample_rate} Hz (Nyquist: {params['nyquist']:.0f} Hz)")
        print(f"  Frequency range: {display_config.fmin} - {params['fmax']:.0f} Hz")
        print(f"  Mel bins: {self.adaptive_n_mels} (scaled from {display_config.n_mels})")

        # Initialize processors
        self.clipping_detector = ClippingDetector(
            sample_rate=audio_config.sample_rate,
            normalization_factor=audio_config.normalization_factor
        )

        # Initialize display state
        self.recording_state = RecordingDisplayState()

        # Initialize controllers
        self.zoom_controller = ZoomController()
        self.zoom_controller.zoom_levels = self.ZOOM_LEVELS
        self.playback_controller = PlaybackController()

        # Initialize display
        self._init_display()

        # Initialize visualizers (need axes)
        self.clipping_visualizer = ClippingVisualizer(self.ax)

        # Initialize handlers
        self.recording_handler = RecordingHandler(
            self.mel_processor,
            self.clipping_detector,
            self.clipping_visualizer,
            self.spec_frames,
            self.adaptive_n_mels,
            audio_config.sample_rate
        )

        self.playback_handler = PlaybackHandler(
            self.parent,
            self.ax,
            self.playback_controller,
            self.zoom_controller,
            self.spec_frames
        )

        self.recording_display = RecordingDisplay(
            self.clipping_detector,
            self.clipping_visualizer,
            self.zoom_controller,
            self.spec_frames,
            display_config
        )

        # Set up callbacks
        self.playback_handler.on_update_display = self._update_spectrogram_view
        self.playback_handler.on_update_time_axis = self._update_time_axis
        self.playback_handler.on_draw_idle = self.draw_idle

        # Initialize state
        self._init_state()

        # Create initial spectrogram image
        self._create_spectrogram_image()

        # Set up event bindings
        self._setup_event_bindings()

        # Audio queue for thread-safe updates
        self.audio_queue = queue.Queue(maxsize=100)

    # Properties for compatibility
    @property
    def spec_buffer(self) -> np.ndarray:
        """Get current spectrogram buffer."""
        return self.recording_handler.spec_buffer

    @spec_buffer.setter
    def spec_buffer(self, value: np.ndarray) -> None:
        """Set spectrogram buffer."""
        self.recording_handler.spec_buffer = value

    @property
    def all_spec_frames(self) -> List[np.ndarray]:
        """Get all recorded spec frames."""
        return self._get_all_spec_frames()

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording_handler.is_recording

    @property
    def frame_count(self) -> int:
        """Get current frame count."""
        return self.recording_handler.frame_count

    @property
    def recording_duration(self) -> float:
        """Get recording duration."""
        return self.recording_display.recording_duration

    def _init_state(self) -> None:
        """Initialize widget state."""
        self.zoom_indicator = None
        self.current_time = 0
        self.max_detected_freq = 0.0

    def _create_spectrogram_image(self) -> None:
        """Create the initial spectrogram image."""
        initial_data = np.ones((self.adaptive_n_mels, self.spec_frames)) * AudioConstants.DB_MIN

        self.im = self.ax.imshow(
            initial_data,
            aspect='auto',
            origin='lower',
            cmap='viridis',
            interpolation='bilinear',
            vmin=AudioConstants.DB_MIN,
            vmax=AudioConstants.DB_MAX
        )

        # Set initial axes
        self.freq_axis_manager.update_default_axis(
            self.adaptive_n_mels,
            self.mel_processor.fmin,
            self.mel_processor.actual_fmax
        )
        self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)

    def _setup_event_bindings(self) -> None:
        """Set up mouse and keyboard event bindings."""
        # Mouse wheel for zoom
        self.canvas_widget.bind('<MouseWheel>', self._on_mouse_wheel)
        self.canvas_widget.bind('<Button-4>', self._on_mouse_wheel)  # Linux
        self.canvas_widget.bind('<Button-5>', self._on_mouse_wheel)  # Linux

        # Double-click to reset zoom
        self.canvas_widget.bind('<Double-Button-1>', self._reset_zoom)

    # Recording methods
    def start_recording(self) -> None:
        """Start recording animation."""
        self.recording_handler.start_recording()

        # Clear display
        self.spec_buffer = self.recording_handler.get_current_spec_buffer()
        self.update_display_data(self.spec_buffer)

        # Reset time axis
        self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)

    def stop_recording(self) -> None:
        """Stop recording animation."""
        self.recording_handler.stop_recording()

    def update_audio(self, audio_chunk: np.ndarray) -> None:
        """Update with new audio data during recording."""
        try:
            # Non-blocking put
            self.audio_queue.put_nowait(audio_chunk)
        except queue.Full:
            # Skip if queue is full
            pass

    def _update_display(self) -> None:
        """Update display from audio queue."""
        # Process all pending audio chunks
        chunks_processed = 0
        while not self.audio_queue.empty() and chunks_processed < 10:
            try:
                audio_chunk = self.audio_queue.get_nowait()
                should_update = self.recording_handler.update_audio(audio_chunk)

                if should_update:
                    # Update display
                    self.update_display_data(self.recording_handler.get_current_spec_buffer())

                    # Update time tracking
                    self.current_time = self.recording_handler.current_time
                    self.max_detected_freq = self.recording_handler.max_detected_freq

                    # Update clipping markers
                    self._update_clipping_markers_live()

                chunks_processed += 1

            except queue.Empty:
                break

        # Update frequency display
        if self.recording_handler.is_recording or self.playback_controller.is_playing:
            self._update_frequency_display()

        self.draw_idle()

    # Playback methods
    def start_playback(self, duration: float) -> None:
        """Start playback animation."""
        recording_duration = self.recording_display.recording_duration
        if recording_duration <= 0:
            recording_duration = self.recording_handler.current_time

        self.playback_handler.start_playback(duration, recording_duration)

    def stop_playback(self) -> None:
        """Stop playback animation."""
        self.playback_handler.stop_playback()

    # Display methods
    def show_recording(self, audio_data: np.ndarray, sample_rate: int) -> None:
        """Display a complete recording."""
        # Process recording
        display_data, adaptive_n_mels, duration = self.recording_display.process_recording(
            audio_data, sample_rate
        )

        # Store recording-specific parameters for frequency display
        self._recording_n_mels = adaptive_n_mels
        self._recording_sample_rate = sample_rate
        self._recording_fmax = sample_rate / 2

        # Check if we need to recreate the image due to shape change
        current_shape = self.im.get_array().shape if self.im else None
        if current_shape and (current_shape[0] != adaptive_n_mels or current_shape[1] != self.spec_frames):
            # Remove old image
            self.im.remove()
            # Create new image with correct dimensions
            self.im = self.ax.imshow(
                display_data,
                aspect='auto',
                origin='lower',
                cmap='viridis',
                interpolation='bilinear',
                vmin=AudioConstants.DB_MIN,
                vmax=AudioConstants.DB_MAX,
                extent=[0, self.spec_frames - 1, 0, adaptive_n_mels - 1]
            )
        else:
            # Update existing image
            self.update_display_data(display_data)
            self.im.set_extent([0, self.spec_frames - 1, 0, adaptive_n_mels - 1])

        # Update clipping markers
        n_frames = len(self.recording_display.all_spec_frames)
        self.clipping_visualizer.update_markers_for_display(n_frames, self.spec_frames)
        self.clipping_visualizer.show_warning()

        # Store max frequency for later
        self.max_detected_freq = self.recording_display.max_detected_freq

        # Update frequency axis for recording
        self._update_frequency_axis_for_recording(sample_rate)

        # Update time axis
        self._update_time_axis(0, duration)

        # IMPORTANT: Set y-axis limits AFTER frequency axis update
        self.ax.set_ylim(0, adaptive_n_mels - 1)

        # Update frequency display (including max freq indicator) AFTER setting ylim
        self._update_frequency_display()

        # Force proper layout with adaptive sizing
        self._apply_adaptive_layout()
        self.ax.set_xlim(0, self.spec_frames - 1)
        self.canvas.draw()

    def clear(self) -> None:
        """Clear the spectrogram display."""
        self.recording_handler.clear()
        self.recording_display.all_spec_frames = []
        self.recording_display.recording_duration = 0
        self.zoom_controller.set_recording_duration(0)

        self.recording_state.clear()
        self.clipping_visualizer.clear()

        # Reset frequency axis
        self._update_frequency_axis()

        # Reset display
        empty_data = np.ones((self.adaptive_n_mels, self.spec_frames)) * AudioConstants.DB_MIN
        self.update_display_data(empty_data)
        self.im.set_extent([0, self.spec_frames - 1, 0, self.adaptive_n_mels - 1])

        # Reset y-axis to default range
        self.ax.set_ylim(0, self.adaptive_n_mels - 1)

        # Reset recording-specific parameters
        if hasattr(self, '_recording_n_mels'):
            delattr(self, '_recording_n_mels')
        if hasattr(self, '_recording_sample_rate'):
            delattr(self, '_recording_sample_rate')
        if hasattr(self, '_recording_fmax'):
            delattr(self, '_recording_fmax')

        self.draw_idle()

    # Zoom methods
    def _on_mouse_wheel(self, event) -> None:
        """Handle mouse wheel zoom events."""
        mouse_rel_x = self._get_mouse_position_in_axes(event)
        if mouse_rel_x is None:
            return

        zoom_in = event.num == 4 or event.delta > 0

        current_time = self.recording_handler.current_time
        if self.zoom_controller.apply_zoom_at_position(mouse_rel_x, zoom_in, current_time):
            self._update_after_zoom()

    def _get_mouse_position_in_axes(self, event) -> Optional[float]:
        """Get mouse position relative to axes (0-1)."""
        bbox = self.ax.get_position()
        fig_width = self.fig.get_figwidth() * self.fig.dpi

        ax_left = bbox.x0 * fig_width
        ax_width = bbox.width * fig_width

        mouse_rel_x = (event.x - ax_left) / ax_width

        if mouse_rel_x < 0 or mouse_rel_x > 1:
            return None

        return mouse_rel_x

    def _reset_zoom(self, event=None) -> None:
        """Reset zoom to 1x."""
        self.zoom_controller.reset()

        # Update time axis
        if self.recording_display.recording_duration > 0:
            self._update_time_axis(0, self.recording_display.recording_duration)
        else:
            self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)

        # Hide zoom indicator
        if self.zoom_indicator:
            self.zoom_indicator.set_visible(False)

        # Update display
        if self.recording_display.all_spec_frames:
            self._update_spectrogram_view()

        self.draw_idle()

    def _update_after_zoom(self) -> None:
        """Update display after zoom change."""
        # Update zoom indicator
        self._update_zoom_indicator()

        # Update time axis
        visible_seconds = self.zoom_controller.get_visible_seconds()
        self._update_time_axis(
            self.zoom_controller.view_offset,
            self.zoom_controller.view_offset + visible_seconds
        )

        # Update spectrogram view
        if self.recording_display.all_spec_frames or self.recording_handler.all_spec_frames:
            self._update_spectrogram_view()

        self.draw_idle()

    def _update_zoom_indicator(self) -> None:
        """Update or create zoom indicator text."""
        if self.recording_display.recording_duration > 0:
            visible_seconds = self.recording_display.recording_duration / self.zoom_controller.zoom_level
        else:
            visible_seconds = UIConstants.SPECTROGRAM_DISPLAY_SECONDS / self.zoom_controller.zoom_level

        indicator_text = f"Zoom: {self.zoom_controller.zoom_level:.1f}x ({visible_seconds:.2f}s)"

        if self.zoom_indicator:
            self.zoom_indicator.set_text(indicator_text)
            self.zoom_indicator.set_visible(True)
        else:
            self.zoom_indicator = self.ax.text(
                0.98, 0.95, indicator_text,
                transform=self.ax.transAxes,
                ha='right', va='top',
                color='white',
                fontsize=self.ZOOM_INDICATOR_FONTSIZE,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7)
            )

        # Auto-hide after delay
        if self.zoom_controller.zoom_level == 1.0:
            self.canvas_widget.after(self.ZOOM_INDICATOR_HIDE_DELAY_MS, self._hide_zoom_indicator)

    def _hide_zoom_indicator(self) -> None:
        """Hide zoom indicator if still at 1x."""
        if self.zoom_controller.zoom_level == 1.0 and self.zoom_indicator:
            self.zoom_indicator.set_visible(False)
            self.draw_idle()

    # Update methods
    def _update_spectrogram_view(self) -> None:
        """Update spectrogram display based on zoom/offset."""
        # Get the correct frame source
        all_frames = self._get_all_spec_frames()
        if all_frames:
            if self.recording_display.recording_duration > 0:
                self._update_recording_view()
            else:
                self._update_live_view()

    def _get_all_spec_frames(self) -> List[np.ndarray]:
        """Get the current spec frames from the appropriate source."""
        if self.recording_display.all_spec_frames:
            return self.recording_display.all_spec_frames
        else:
            return self.recording_handler.all_spec_frames

    def _update_recording_view(self) -> None:
        """Update view for loaded recordings."""
        start_frame, end_frame = self.recording_display.calculate_visible_frame_range()
        visible_frames = self.recording_display.get_visible_frames(start_frame, end_frame)

        if visible_frames:
            self._display_resampled_frames(visible_frames, start_frame, end_frame)

    def _update_live_view(self) -> None:
        """Update view for live recording."""
        start_frame = int(self.zoom_controller.view_offset * self.frames_per_second)
        visible_frames = int((UIConstants.SPECTROGRAM_DISPLAY_SECONDS / self.zoom_controller.zoom_level) * self.frames_per_second)
        end_frame = min(start_frame + visible_frames, len(self.recording_handler.all_spec_frames))

        if start_frame < len(self.recording_handler.all_spec_frames):
            visible_data = self.recording_handler.all_spec_frames[start_frame:end_frame]

            if visible_data:
                visible_array = np.array(visible_data).T
                self.update_display_data(visible_array)

    def _display_resampled_frames(self, visible_frames: List[np.ndarray],
                                 start_frame: int, end_frame: int) -> None:
        """Display resampled frames with proper clipping markers."""
        visible_array = np.array(visible_frames).T
        n_mels = visible_array.shape[0]
        n_frames_visible = visible_array.shape[1]

        if n_frames_visible > 1:
            # Resample to fit display
            resampled = self._resample_frames_to_display(visible_array, n_mels, n_frames_visible)
            self.update_display_data(resampled)
        else:
            self.update_display_data(visible_array)

        # Update extent
        self.im.set_extent([0, self.spec_frames - 1, 0, n_mels - 1])

        # Update clipping markers
        self.clipping_visualizer.update_markers_for_zoom(start_frame, end_frame, self.spec_frames)
        self.clipping_visualizer.show_warning()

    def _update_clipping_markers_live(self) -> None:
        """Update clipping markers during live recording."""
        self.clipping_visualizer.update_markers_for_live(
            self.current_time,
            self.recording_handler.frame_count,
            self.spec_frames,
            self.frames_per_second,
            self.zoom_controller.zoom_level
        )
        self.clipping_visualizer.show_warning()

    def _update_frequency_axis(self) -> None:
        """Update frequency axis to default."""
        self.freq_axis_manager.update_default_axis(
            self.adaptive_n_mels,
            self.mel_processor.fmin,
            self.mel_processor.actual_fmax
        )

    def _update_frequency_axis_for_recording(self, sample_rate: int) -> None:
        """Update frequency axis for a specific recording."""
        params = MelProcessorFactory.calculate_adaptive_params(sample_rate, self.display_config.fmin)

        # Calculate adaptive parameters
        nyquist_freq = sample_rate / 2
        freq_range = nyquist_freq - self.display_config.fmin
        mel_scale_factor = freq_range / self.BASE_FREQ_RANGE
        adaptive_n_mels = max(self.MIN_ADAPTIVE_MELS, int(self.BASE_MEL_BINS * mel_scale_factor))

        # Update frequency axis using the recording_axis method
        actual_n_mels, actual_fmax = self.freq_axis_manager.update_recording_axis(
            sample_rate,
            self.display_config.fmin
        )

    def _update_frequency_display(self) -> None:
        """Update highest frequency display."""
        if self.max_detected_freq > 0:
            # Use recording-specific parameters if available
            n_mels = getattr(self, '_recording_n_mels', self.adaptive_n_mels)
            fmax = getattr(self, '_recording_fmax', self.mel_processor.actual_fmax)

            self.freq_axis_manager.highlight_max_frequency(
                self.max_detected_freq,
                n_mels,
                self.mel_processor.fmin,
                fmax
            )

    # Schedule display updates
    def _on_spec_frames_changed(self, old_frames: int, new_frames: int) -> None:
        """Handle spec_frames change due to window resize."""
        # Update handlers with new spec_frames
        self.recording_handler.spec_frames = new_frames
        self.playback_handler.spec_frames = new_frames
        self.recording_display.spec_frames = new_frames

        # Recreate spectrogram image with new dimensions
        if self.im:
            self.im.remove()
            self._create_spectrogram_image()

        # Update time axis to ensure full time range is shown
        if self.recording_display.recording_duration > 0:
            self._update_time_axis(0, self.recording_display.recording_duration)
        else:
            self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)

        # Redisplay current content if any
        if self.recording_display.all_spec_frames:
            # Reprocess the display data for new width
            self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display after spec_frames change."""
        if self.recording_display.recording_duration > 0:
            # We have a loaded recording - update it
            display_data = self.recording_display._resample_spectrogram_for_display(
                np.array(self.recording_display.all_spec_frames).T,
                len(self.recording_display.all_spec_frames),
                self._recording_n_mels if hasattr(self, '_recording_n_mels') else self.adaptive_n_mels
            )
            self.update_display_data(display_data)
            self.canvas.draw()

    def schedule_update(self) -> None:
        """Schedule a display update (called from main app)."""
        self._update_display()