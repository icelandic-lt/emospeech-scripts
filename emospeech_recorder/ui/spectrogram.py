"""Mel Spectrogram widget for real-time audio visualization."""

from typing import Optional, List, Tuple
import numpy as np
import tkinter as tk
from tkinter import ttk
import queue
import time
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D
from matplotlib.text import Text
import librosa

from ..constants import AudioConstants, UIConstants
from ..audio.processor import MelSpectrogramProcessor, ClippingDetector
from ..utils.config import AudioConfig, DisplayConfig


class MelSpectrogramWidget:
    """Real-time mel spectrogram display widget with clipping detection.

    This widget provides a matplotlib-based visualization of audio in real-time,
    showing mel-scale spectrograms with optional clipping detection markers.
    It supports both live recording visualization and playback of saved recordings.

    The mel spectrogram provides a perceptually-motivated frequency representation
    of speech, with higher resolution at lower frequencies where most speech
    information is concentrated.

    Features:
        - Real-time spectrogram display during recording
        - Clipping detection with visual markers
        - Playback position indicator
        - Configurable display parameters (time window, frequency range)
        - Smooth scrolling for long recordings

    Attributes:
        parent: Parent tkinter widget
        audio_config: Audio configuration (sample rate, bit depth)
        display_config: Display settings (mel bands, frequency range)
        mel_processor: Processor for computing mel spectrograms
        clipping_detector: Detector for audio clipping
        spec_buffer: Buffer holding spectrogram data for display
        audio_buffer: Rolling buffer of audio samples
        fig: Matplotlib figure
        ax: Matplotlib axes
        im: Matplotlib image showing the spectrogram
        canvas: Tkinter canvas for matplotlib integration
    """

    def __init__(self,
                 parent: tk.Widget,
                 audio_config: AudioConfig,
                 display_config: DisplayConfig,
                 shared_state: dict = None):
        """Initialize the mel spectrogram widget.

        Args:
            parent: Parent tkinter widget to contain the spectrogram
            audio_config: Audio configuration with sample rate and format
            display_config: Display configuration with mel parameters
        """
        self.parent = parent
        self.audio_config = audio_config
        self.display_config = display_config
        self.shared_state = shared_state or {}

        # Calculate derived values
        self.frames_per_second = audio_config.sample_rate / AudioConstants.HOP_LENGTH
        self.spec_frames = int(display_config.display_seconds * self.frames_per_second)
        self.time_per_frame = AudioConstants.HOP_LENGTH / audio_config.sample_rate

        # Initialize processors
        self.mel_processor = MelSpectrogramProcessor(
            sample_rate=audio_config.sample_rate,
            n_mels=display_config.n_mels,
            fmin=display_config.fmin,
            fmax=display_config.fmax
        )

        self.clipping_detector = ClippingDetector(
            sample_rate=audio_config.sample_rate,
            normalization_factor=audio_config.normalization_factor
        )

        # Initialize buffers
        self._init_buffers()

        # Initialize display
        self._init_display()

        # Initialize state
        self._init_state()

    def _init_buffers(self) -> None:
        """Initialize audio and spectrogram buffers.

        Creates:
            - Audio buffer: Rolling buffer for incoming audio samples
            - Spectrogram buffer: 2D array for mel spectrogram display
            - Audio queue: Thread-safe queue for inter-thread communication
        """
        # Audio buffer for spectrogram computation
        self.buffer_size = int(UIConstants.SPECTROGRAM_DISPLAY_SECONDS * self.audio_config.sample_rate)
        self.audio_buffer = np.zeros(self.buffer_size)

        # Spectrogram display buffer
        self.spec_buffer = np.ones((self.display_config.n_mels, self.spec_frames)) * AudioConstants.DB_MIN

        # Thread-safe queue for audio data
        self.audio_queue = queue.Queue(maxsize=100)

    def _init_display(self) -> None:
        """Initialize matplotlib display components.

        Sets up the matplotlib figure, axes, and spectrogram image.
        Configures visual appearance including colors, labels, and
        grid settings for optimal speech visualization.
        """
        # Create figure
        self.fig = Figure(
            figsize=(UIConstants.SPECTROGRAM_WIDTH_INCHES, UIConstants.SPECTROGRAM_HEIGHT_INCHES),
            dpi=UIConstants.SPECTROGRAM_DPI,
            facecolor=UIConstants.COLOR_BACKGROUND
        )

        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(UIConstants.COLOR_BACKGROUND)

        # Configure axes
        self._configure_axes()

        # Create spectrogram image
        self.im = self.ax.imshow(
            self.spec_buffer,
            aspect='auto',
            origin='lower',
            cmap='viridis',
            interpolation='bilinear',
            vmin=AudioConstants.DB_MIN,
            vmax=AudioConstants.DB_MAX
        )
        if self.shared_state.get('debug', False):
            print(f"Spectrogram imshow created: vmin={AudioConstants.DB_MIN}, vmax={AudioConstants.DB_MAX}")
            print(f"Initial spec_buffer range: [{np.min(self.spec_buffer):.1f}, {np.max(self.spec_buffer):.1f}]")

        # Set initial frequency axis
        self._update_frequency_axis()

        # Set initial time axis
        self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.parent)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)
        self.canvas_widget.config(
            bg=UIConstants.COLOR_BACKGROUND,
            highlightthickness=1,
            highlightbackground=UIConstants.COLOR_TEXT_INACTIVE
        )

        # Initial draw with adjusted margins
        self.fig.tight_layout(rect=[0, 0, 0.98, 1])  # Leave space for right-side label
        self.canvas.draw()

    def _configure_axes(self) -> None:
        """Configure axes appearance.

        Sets up axis labels, tick marks, spine visibility, and colors
        to match the application's dark theme.
        """
        # Remove x-axis label to save vertical space
        self.ax.set_xlabel('', fontsize=UIConstants.AXIS_LABEL_FONTSIZE)
        self.ax.set_ylabel('Frequency (Hz)', color=UIConstants.COLOR_TEXT_INACTIVE,
                          fontsize=UIConstants.AXIS_LABEL_FONTSIZE)
        self.ax.tick_params(colors=UIConstants.COLOR_TEXT_INACTIVE,
                           labelsize=UIConstants.AXIS_TICK_FONTSIZE)

        # Add "Time (s)" as text annotation at the right side
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

    def _init_state(self) -> None:
        """Initialize widget state.

        Sets up internal state variables for recording, playback,
        and animation tracking.
        """
        # Recording state
        self.is_recording = False
        self.update_counter = 0
        self.pending_update = False
        self.frame_count = 0

        # Time tracking
        self.recording_start_time = 0
        self.current_time = 0

        # Playback state
        self.playback_line: Optional[Line2D] = None
        self.playback_position = 0.0
        self.playback_duration = 0.0
        self.is_playing = False
        self.animation_id: Optional[int] = None

        # Clipping detection
        self.clipping_markers: List[int] = []
        self.clipping_warning: Optional[Text] = None

    def _update_frequency_axis(self) -> None:
        """Update frequency axis labels.

        Maps mel bin indices to frequency values in Hz for
        the y-axis labels using logarithmic spacing.
        """
        # Get mel scale frequencies
        mel_freqs = librosa.mel_frequencies(
            n_mels=self.display_config.n_mels + 2,  # +2 for edge bins
            fmin=self.display_config.fmin,
            fmax=self.display_config.fmax
        )[1:-1]  # Remove edge bins

        # Select frequencies to display with more emphasis on lower frequencies
        # Create custom spacing with more ticks in lower frequencies
        n_ticks = UIConstants.N_FREQUENCY_TICKS

        # Split ticks: more in lower half, fewer in upper half
        lower_ticks = int(n_ticks * 0.6)  # 60% of ticks for lower frequencies
        upper_ticks = n_ticks - lower_ticks

        # Lower frequency range (0 to 1/3 of mel range) - more detail
        lower_indices = np.linspace(0, self.display_config.n_mels // 3,
                                   lower_ticks, dtype=int)

        # Upper frequency range (1/3 to end) - less detail
        upper_indices = np.linspace(self.display_config.n_mels // 3 + 1,
                                   self.display_config.n_mels - 1,
                                   upper_ticks, dtype=int)

        # Combine and ensure uniqueness
        log_indices = np.unique(np.concatenate([lower_indices, upper_indices]))

        # Always include first and last
        log_indices[0] = 0
        log_indices[-1] = self.display_config.n_mels - 1

        yticks = log_indices
        yticklabels = []
        for idx in log_indices:
            freq = mel_freqs[idx]
            if freq < 1000:
                yticklabels.append(f'{int(freq)}')
            else:
                yticklabels.append(f'{freq/1000:.1f}k')

        self.ax.set_yticks(yticks)
        self.ax.set_yticklabels(yticklabels)

    def _update_time_axis(self, start_time: float, end_time: float) -> None:
        """Update time axis labels.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
        """
        time_labels = np.linspace(start_time, end_time, UIConstants.N_TIME_TICKS)
        xticks = np.linspace(0, self.spec_frames - 1, UIConstants.N_TIME_TICKS)
        self.ax.set_xticks(xticks)
        self.ax.set_xticklabels([f'{t:.1f}' for t in time_labels])

    def update_audio(self, audio_chunk: np.ndarray) -> None:
        """Process audio data and schedule UI update.

        Called from the audio transfer thread with chunks of audio data.
        Updates the rolling buffer, computes mel spectrograms, and
        schedules display updates in the main UI thread.

        Args:
            audio_chunk: Audio samples from the recording process

        Note:
            This method is called from a background thread, so UI
            updates are scheduled via parent.after() for thread safety.
        """
        # Ensure we have a valid chunk
        if audio_chunk is None or len(audio_chunk) == 0:
            return

        # Debug first chunk
        if self.update_counter == 0 and self.shared_state.get('debug', False):
            print(f"MelSpectrogram first chunk: shape={audio_chunk.shape}, dtype={audio_chunk.dtype}")
            print(f"is_recording={self.is_recording}, norm_factor={self.audio_config.normalization_factor}")

        if not self.is_recording:
            if self.update_counter == 0 and self.shared_state.get('debug', False):
                print(f"WARNING: update_audio called but is_recording=False")
            return

        # Update audio buffer
        chunk_size = len(audio_chunk)
        self.audio_buffer = np.roll(self.audio_buffer, -chunk_size)
        self.audio_buffer[-chunk_size:] = audio_chunk.flatten()

        self.update_counter += 1

        # Update current time
        self.current_time += chunk_size / self.audio_config.sample_rate

        # Check for clipping
        if self.clipping_detector.process(audio_chunk):
            clipping_pos = self.frame_count
            if (not self.clipping_markers or
                clipping_pos - self.clipping_markers[-1] > AudioConstants.MIN_CLIPPING_MARKER_DISTANCE):
                self.clipping_markers.append(clipping_pos)
                if self.shared_state.get('debug', False):
                    print(f"Clipping detected at frame {clipping_pos}, time {self.current_time:.2f}s")

        # Process spectrogram at reduced rate
        if self.update_counter % 2 == 0:
            # Extract frame for processing
            frame = self.audio_buffer[-AudioConstants.N_FFT:]

            # Compute mel spectrogram
            mel_db = self.mel_processor.process(frame, self.audio_config.normalization_factor)

            # Debug: Print mel_db values periodically
            if self.frame_count % 50 == 0 and self.shared_state.get('debug', False):
                print(f"Frame {self.frame_count}: mel_db range [{np.min(mel_db):.1f}, {np.max(mel_db):.1f}]")
                print(f"spec_buffer range before update: [{np.min(self.spec_buffer):.1f}, {np.max(self.spec_buffer):.1f}]")

            # Update spectrogram buffer
            self.spec_buffer = np.roll(self.spec_buffer, -1, axis=1)
            self.spec_buffer[:, -1] = mel_db
            self.frame_count += 1

            # Schedule UI update
            if not self.pending_update:
                self.pending_update = True
                if self.shared_state.get('debug', False):
                    print(f"Scheduling UI update for frame {self.frame_count}")
                self.parent.after(0, self._update_display)
            else:
                if self.shared_state.get('debug', False):
                    print(f"UI update already pending for frame {self.frame_count}")

    def _update_display(self) -> None:
        """Update display in main thread.

        Called via after() to update the matplotlib display with
        the latest spectrogram data. Handles scrolling for long
        recordings and updates clipping markers.

        Note:
            Must be called from the main UI thread.
        """
        if self.shared_state.get('debug', False):
            print(f"_update_display called for frame {self.frame_count}")
        try:
            # Debug: Check spec_buffer content
            if self.shared_state.get('debug', False):
                print(f"Display update {self.frame_count}: spec_buffer shape={self.spec_buffer.shape}")
                print(f"  spec_buffer range: [{np.min(self.spec_buffer):.1f}, {np.max(self.spec_buffer):.1f}]")
                print(f"  spec_buffer non-default values: {np.sum(self.spec_buffer != AudioConstants.DB_MIN)}")

            # Update spectrogram
            self.im.set_data(self.spec_buffer)

            # Update clipping markers
            self._update_clipping_markers()

            # Update time axis
            if self.current_time <= UIConstants.SPECTROGRAM_DISPLAY_SECONDS:
                self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)
            else:
                start_time = self.current_time - UIConstants.SPECTROGRAM_DISPLAY_SECONDS
                self._update_time_axis(start_time, self.current_time)

            self.canvas.draw()
            self.pending_update = False

        except Exception as e:
            if self.shared_state.get('debug', False):
                print(f"Error updating display: {e}")
                import traceback
                traceback.print_exc()

    def _update_clipping_markers(self) -> None:
        """Update clipping marker display.

        Removes old markers and adds new ones based on current
        view window. Markers indicate where audio clipping occurred.
        """
        # Remove old markers
        for line in self.ax.lines[:]:
            if hasattr(line, '_is_clipping_marker') and line._is_clipping_marker:
                line.remove()

        # Add visible markers
        for clip_pos in self.clipping_markers:
            if self.current_time <= UIConstants.SPECTROGRAM_DISPLAY_SECONDS:
                if clip_pos < self.spec_frames:
                    self._add_clipping_line(clip_pos)
            else:
                start_frame = self.frame_count - self.spec_frames
                if start_frame <= clip_pos < self.frame_count:
                    display_pos = clip_pos - start_frame
                    self._add_clipping_line(display_pos)

        # Update warning
        self._update_clipping_warning()

    def _add_clipping_line(self, x_position: int) -> None:
        """Add a clipping marker line at the specified position.

        Args:
            x_position: Frame position for the marker
        """
        line = self.ax.axvline(
            x=x_position,
            color=UIConstants.COLOR_CLIPPING,
            linewidth=UIConstants.CLIPPING_LINE_WIDTH,
            alpha=UIConstants.CLIPPING_LINE_ALPHA
        )
        line._is_clipping_marker = True

    def _update_clipping_warning(self) -> None:
        """Update clipping warning display.

        Shows or hides a warning symbol when clipping is detected
        in the recording.
        """
        if self.clipping_markers:
            if not self.clipping_warning:
                self.clipping_warning = self.ax.text(
                    UIConstants.CLIPPING_WARNING_POSITION[0],
                    UIConstants.CLIPPING_WARNING_POSITION[1],
                    UIConstants.CLIPPING_WARNING_SYMBOL,
                    transform=self.ax.transAxes,
                    fontsize=UIConstants.CLIPPING_WARNING_SIZE,
                    color=UIConstants.COLOR_CLIPPING,
                    weight='bold',
                    verticalalignment='top'
                )
        else:
            if self.clipping_warning:
                self.clipping_warning.remove()
                self.clipping_warning = None

    def start_recording(self) -> None:
        """Start recording animation.

        Resets state and prepares the widget for displaying
        real-time audio during recording.
        """
        self.is_recording = True
        self.current_time = 0
        self.frame_count = 0
        self.update_counter = 0  # Reset update counter
        self.clipping_markers = []
        self._update_time_axis(0, UIConstants.SPECTROGRAM_DISPLAY_SECONDS)
        if self.shared_state.get('debug', False):
            print(f"MelSpectrogram: Recording started, is_recording={self.is_recording}")

    def stop_recording(self) -> None:
        """Stop recording animation.

        Stops processing new audio chunks for display.
        """
        self.is_recording = False

    def start_playback(self, duration: float) -> None:
        """Start playback animation.

        Shows a moving line indicator during audio playback.

        Args:
            duration: Total duration of the audio being played
        """
        self.stop_playback()  # Stop any existing playback

        self.is_playing = True
        self.playback_duration = duration
        self.playback_position = 0.0
        self.playback_start_time = time.time()  # Record actual start time

        # Create playback line
        if self.playback_line is None:
            self.playback_line = self.ax.axvline(
                x=0,
                color=UIConstants.COLOR_PLAYBACK_LINE,
                linewidth=UIConstants.PLAYBACK_LINE_WIDTH,
                alpha=UIConstants.PLAYBACK_LINE_ALPHA
            )
        else:
            self.playback_line.set_visible(True)
            self.playback_line.set_xdata([0])

        self._update_playback_position()

    def stop_playback(self) -> None:
        """Stop playback animation.

        Hides the playback indicator and cancels animation updates.
        """
        self.is_playing = False

        if self.animation_id:
            self.parent.after_cancel(self.animation_id)
            self.animation_id = None

        if self.playback_line:
            self.playback_line.set_visible(False)

        self.canvas.draw_idle()

    def _update_playback_position(self) -> None:
        """Update playback position indicator.

        Animates the playback line across the spectrogram in sync
        with audio playback. Called periodically via after().
        """
        if not self.is_playing:
            return

        # Calculate actual elapsed time instead of accumulating updates
        actual_elapsed = time.time() - self.playback_start_time
        self.playback_position = actual_elapsed

        if self.playback_duration > 0:
            # Calculate position
            if self.playback_duration < UIConstants.SPECTROGRAM_DISPLAY_SECONDS:
                x_pos = (self.playback_position / UIConstants.SPECTROGRAM_DISPLAY_SECONDS) * (self.spec_frames - 1)
            else:
                x_pos = (self.playback_position / self.playback_duration) * (self.spec_frames - 1)

            x_pos = min(x_pos, self.spec_frames - 1)
            self.playback_line.set_xdata([x_pos])
            self.canvas.draw_idle()

        # Continue animation
        if self.playback_position < self.playback_duration:
            self.animation_id = self.parent.after(
                UIConstants.ANIMATION_UPDATE_MS,
                self._update_playback_position
            )
        else:
            self.stop_playback()

    def clear(self) -> None:
        """Clear the spectrogram display.

        Resets all buffers and removes visual elements, returning
        the display to its initial empty state.
        """
        self.spec_buffer.fill(AudioConstants.DB_MIN)
        self.audio_buffer.fill(0)
        self.clipping_markers = []

        # Remove markers
        for line in self.ax.lines[:]:
            if hasattr(line, '_is_clipping_marker') and line._is_clipping_marker:
                line.remove()

        # Remove warning
        if self.clipping_warning:
            self.clipping_warning.remove()
            self.clipping_warning = None

        self.im.set_data(self.spec_buffer)
        self.canvas.draw_idle()

    def show_recording(self, audio_data: np.ndarray, sample_rate: int) -> None:
        """Display a complete recording.

        Processes and displays a saved recording's spectrogram.
        Handles resampling if necessary and detects clipping.

        Args:
            audio_data: Complete audio signal (normalized -1 to 1)
            sample_rate: Sample rate of the audio

        Note:
            For long recordings, the spectrogram is subsampled to
            fit the display window.
        """
        if self.shared_state.get('debug', False):
            print(f"show_recording called: audio_data shape={audio_data.shape}, sample_rate={sample_rate}")

        # Clear display
        self.spec_buffer.fill(AudioConstants.DB_MIN)
        self.clipping_markers = []

        # Resample if necessary
        if sample_rate != self.audio_config.sample_rate:
            import librosa
            audio_data = librosa.resample(
                audio_data,
                orig_sr=sample_rate,
                target_sr=self.audio_config.sample_rate
            )
            if self.shared_state.get('debug', False):
                print(f"Resampled audio from {sample_rate} to {self.audio_config.sample_rate}")

        # Detect clipping
        self.clipping_markers = self.clipping_detector.find_clipping_positions(audio_data)
        if self.shared_state.get('debug', False):
            print(f"Detected {len(self.clipping_markers)} clipping positions")

        # Process spectrogram
        mel_spec, n_frames = self.mel_processor.process_file(
            audio_data,
            self.audio_config.normalization_factor
        )
        if self.shared_state.get('debug', False):
            print(f"Processed spectrogram: mel_spec shape={mel_spec.shape}, n_frames={n_frames}")
            print(f"mel_spec range: [{np.min(mel_spec):.1f}, {np.max(mel_spec):.1f}]")

        # Display spectrogram
        if n_frames <= self.spec_frames:
            # Recording fits - show all
            self.spec_buffer[:, :n_frames] = mel_spec[:, :n_frames]
            if self.shared_state.get('debug', False):
                print(f"Recording fits in buffer: using first {n_frames} frames")
        else:
            # Recording is longer - sample to fit
            indices = np.linspace(0, n_frames - 1, self.spec_frames, dtype=int)
            self.spec_buffer = mel_spec[:, indices]
            if self.shared_state.get('debug', False):
                print(f"Recording too long: sampling {len(indices)} frames from {n_frames}")

            # Scale clipping markers
            scale_factor = self.spec_frames / n_frames
            self.clipping_markers = [int(pos * scale_factor) for pos in self.clipping_markers]

        if self.shared_state.get('debug', False):
            print(f"Final spec_buffer range: [{np.min(self.spec_buffer):.1f}, {np.max(self.spec_buffer):.1f}]")

        # Update display
        self.im.set_data(self.spec_buffer)
        if self.shared_state.get('debug', False):
            print("Called im.set_data() for saved recording")

        # Update markers
        for line in self.ax.lines[:]:
            if hasattr(line, '_is_clipping_marker') and line._is_clipping_marker:
                line.remove()

        for clip_pos in self.clipping_markers:
            if 0 <= clip_pos < self.spec_frames:
                self._add_clipping_line(clip_pos)

        self._update_clipping_warning()

        # Update time axis
        duration = len(audio_data) / self.audio_config.sample_rate
        self._update_time_axis(0, duration)

        self.canvas.draw()