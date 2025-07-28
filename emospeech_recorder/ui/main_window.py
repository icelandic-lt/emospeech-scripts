"""Main window UI for the EmoSpeech Recorder."""

from typing import Optional, Callable
import tkinter as tk
from tkinter import ttk

from ..constants import UIConstants, KeyBindings
from ..utils.config import UIConfig, RecorderConfig
from ..utils.state import UIState, RecordingState
from .spectrogram import MelSpectrogramWidget
from .icon import AppIcon


class MainWindow:
    """Main application window for the EmoSpeech Recorder.

    This class manages the main UI window, including layout, widget creation,
    font scaling, and window resizing. It provides a three-panel layout:
    - Top info bar: Status, recording indicator, and progress
    - Center content: Current utterance display
    - Bottom control: Mel spectrogram and keyboard shortcuts

    The window supports dynamic font scaling based on window size and
    can toggle between fullscreen and windowed modes.

    Attributes:
        root: Tkinter root window
        config: Application configuration
        recording_state: State manager for recording data
        ui_state: State manager for UI elements
        mel_spectrogram: Optional mel spectrogram visualization widget
        main_frame: Main container frame
        info_frame: Top information bar
        content_frame: Center content area
        control_frame: Bottom control area
    """

    def __init__(self,
                 root: tk.Tk,
                 config: RecorderConfig,
                 recording_state: RecordingState,
                 ui_state: UIState,
                 shared_state: dict = None):
        """Initialize the main window.

        Args:
            root: Tkinter root window
            config: Application configuration with display and UI settings
            recording_state: Recording state manager tracking current utterance
            ui_state: UI state manager for window properties
        """
        self.root = root
        self.config = config
        self.recording_state = recording_state
        self.ui_state = ui_state
        self.shared_state = shared_state or {}

        # Get screen information
        self._setup_screen_geometry()

        # Configure window
        self._setup_window()

        # Create UI elements
        self._create_ui()

        # Bind resize events
        self.root.bind('<Configure>', self._on_window_resize)

    def _setup_screen_geometry(self) -> None:
        """Get screen dimensions and calculate window size.

        Determines screen dimensions and calculates appropriate window
        size based on configuration. Supports both percentage-based
        and absolute pixel dimensions.
        """
        self.root.update_idletasks()

        # Get screen dimensions
        self.ui_state.screen_width = self.root.winfo_screenwidth()
        self.ui_state.screen_height = self.root.winfo_screenheight()

        # Calculate window dimensions
        width_pct, height_pct = self.config.ui.is_window_size_percentage

        if self.config.ui.window_width:
            if width_pct:
                self.ui_state.window_width = int(
                    self.ui_state.screen_width * self.config.ui.window_width / 100
                )
            else:
                self.ui_state.window_width = self.config.ui.window_width
        else:
            self.ui_state.window_width = int(
                self.ui_state.screen_width * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )

        if self.config.ui.window_height:
            if height_pct:
                self.ui_state.window_height = int(
                    self.ui_state.screen_height * self.config.ui.window_height / 100
                )
            else:
                self.ui_state.window_height = self.config.ui.window_height
        else:
            self.ui_state.window_height = int(
                self.ui_state.screen_height * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )

    def _setup_window(self) -> None:
        """Configure the main window.

        Sets window size, position, title, and appearance properties.
        Handles both fullscreen and windowed modes, centering the
        window on screen when not fullscreen.
        """
        if self.config.ui.fullscreen:
            self.root.attributes('-fullscreen', True)
            self.ui_state.window_width = self.ui_state.screen_width
            self.ui_state.window_height = self.ui_state.screen_height
        else:
            # Set window size
            self.root.geometry(f"{self.ui_state.window_width}x{self.ui_state.window_height}")

            # Center window
            x = (self.ui_state.screen_width - self.ui_state.window_width) // 2
            y = (self.ui_state.screen_height - self.ui_state.window_height) // 2
            self.root.geometry(f"{self.ui_state.window_width}x{self.ui_state.window_height}+{x}+{y}")

        # Set minimum window size
        self.root.minsize(800, 600)

        # Window properties
        self.root.title("EmoSpeech Recorder")
        self.root.resizable(True, True)
        self.root.configure(bg=UIConstants.COLOR_BACKGROUND)

        # Set window icon
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        """Set the window icon.

        Creates a custom microphone icon for the application window.
        Falls back to a simple icon if the detailed one fails.
        """
        try:
            # Try to create the icon
            icon = AppIcon.create_icon()
            if icon:
                self.root.iconphoto(True, icon)
                # For macOS dock icon
                self.root.wm_iconphoto(True, icon)
        except Exception as e:
            # Icon setting failed, but that's okay
            if self.shared_state.get('debug', False):
                print(f"Could not set window icon: {e}")

    def _create_ui(self) -> None:
        """Create the UI elements.

        Creates the three-panel layout with appropriate spacing and padding.
        Initializes all UI widgets and applies initial font sizes.
        """
        # Main container
        self.main_frame = tk.Frame(self.root, bg=UIConstants.COLOR_BACKGROUND)
        self.main_frame.pack(
            fill=tk.BOTH,
            expand=True,
            padx=UIConstants.MAIN_FRAME_PADDING,
            pady=UIConstants.MAIN_FRAME_PADDING
        )

        # Top info bar
        self._create_info_bar()

        # Center content area
        self._create_content_area()

        # Bottom control area
        self._create_control_area()

        # Calculate initial font sizes
        self._calculate_font_sizes()

        # Apply fonts
        self._apply_fonts()

    def _create_info_bar(self) -> None:
        """Create the top information bar.

        Creates the status display, recording indicator, and progress
        counter. The bar height is proportional to window height.
        """
        height = int(self.ui_state.window_height * UIConstants.INFO_FRAME_HEIGHT_RATIO)

        self.info_frame = tk.Frame(
            self.main_frame,
            bg=UIConstants.COLOR_BACKGROUND,
            height=height
        )
        self.info_frame.pack(fill=tk.X, pady=(0, UIConstants.FRAME_SPACING))
        self.info_frame.pack_propagate(False)

        # Status text
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(
            self.info_frame,
            textvariable=self.status_var,
            fg=UIConstants.COLOR_TEXT_INACTIVE,
            bg=UIConstants.COLOR_BACKGROUND
        )
        self.status_label.pack(side=tk.LEFT, padx=UIConstants.FRAME_SPACING)

        # Recording indicator
        self.rec_indicator = tk.Label(
            self.info_frame,
            text="● REC",
            fg=UIConstants.COLOR_TEXT_INACTIVE,
            bg=UIConstants.COLOR_BACKGROUND
        )
        self.rec_indicator.pack(side=tk.RIGHT, padx=UIConstants.FRAME_SPACING)

        # Progress info
        self.progress_var = tk.StringVar()
        self.progress_label = tk.Label(
            self.info_frame,
            textvariable=self.progress_var,
            fg=UIConstants.COLOR_TEXT_INACTIVE,
            bg=UIConstants.COLOR_BACKGROUND
        )
        self.progress_label.pack(side=tk.RIGHT, padx=UIConstants.MAIN_FRAME_PADDING)

    def _create_content_area(self) -> None:
        """Create the center content area.

        Creates the main display area showing the current utterance
        label and text. Text is centered and wraps based on window width.
        """
        self.content_frame = tk.Frame(
            self.main_frame,
            bg=UIConstants.COLOR_BACKGROUND
        )
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Label for utterance ID
        self.label_var = tk.StringVar()
        self.label_display = tk.Label(
            self.content_frame,
            textvariable=self.label_var,
            fg=UIConstants.COLOR_TEXT_NORMAL,
            bg=UIConstants.COLOR_BACKGROUND,
            anchor="w"
        )
        self.label_display.pack(pady=(0, UIConstants.FRAME_SPACING))

        # Main text display
        self.text_var = tk.StringVar()
        self.text_display = tk.Label(
            self.content_frame,
            textvariable=self.text_var,
            fg=UIConstants.COLOR_TEXT_NORMAL,
            bg=UIConstants.COLOR_BACKGROUND,
            anchor="center",
            justify="center"
        )
        self.text_display.pack(expand=True)

    def _create_control_area(self) -> None:
        """Create the bottom control area.

        Creates the bottom panel containing the optional mel spectrogram
        widget and keyboard shortcuts help text. Height is proportional
        to window size.
        """
        height = int(self.ui_state.window_height * UIConstants.CONTROL_FRAME_HEIGHT_RATIO)

        self.control_frame = tk.Frame(
            self.main_frame,
            bg=UIConstants.COLOR_BACKGROUND,
            height=height
        )
        self.control_frame.pack(fill=tk.X, pady=(UIConstants.FRAME_SPACING, 0))
        self.control_frame.pack_propagate(False)

        # Create spectrogram widget if enabled
        if self.config.display.show_spectrogram:
            self._create_spectrogram_widget()

        # Keyboard shortcuts help
        help_text = "SPACE: Record | P: Play | ↑↓: Navigate | ←→: Browse Takes | D: Delete | M: Toggle Mel | Q: Quit | F11: Full"
        self.help_label = tk.Label(
            self.control_frame,
            text=help_text,
            fg=UIConstants.COLOR_TEXT_INACTIVE,
            bg=UIConstants.COLOR_BACKGROUND
        )
        self.help_label.pack(side=tk.BOTTOM, pady=5)

    def _create_spectrogram_widget(self) -> None:
        """Create the mel spectrogram widget.

        Creates a frame and initializes the MelSpectrogramWidget for
        real-time audio visualization. Only created if spectrogram
        display is enabled in configuration.
        """
        # Create frame for spectrogram
        self.spec_frame = tk.Frame(
            self.control_frame,
            bg=UIConstants.COLOR_BACKGROUND,
            height=200
        )
        self.spec_frame.pack(
            fill=tk.BOTH,
            expand=True,
            padx=UIConstants.FRAME_SPACING,
            pady=(0, UIConstants.FRAME_SPACING)
        )
        self.spec_frame.pack_propagate(False)

        # Create mel spectrogram widget
        self.mel_spectrogram = MelSpectrogramWidget(
            self.spec_frame,
            self.config.audio,
            self.config.display,
            self.shared_state
        )

        self.ui_state.spectrogram_visible = True

    def _calculate_font_sizes(self) -> None:
        """Calculate dynamic font sizes based on window dimensions.

        Scales fonts proportionally to window size to maintain
        readability at different resolutions. Uses a base font size
        from configuration and applies scaling factors.
        """
        # Scale factor based on window size
        scale_factor = min(
            self.ui_state.window_width / 1200,
            self.ui_state.window_height / 900
        )

        self.ui_state.calculate_font_sizes(
            self.config.ui.base_font_size,
            scale_factor
        )

    def _apply_fonts(self) -> None:
        """Apply calculated fonts to widgets.

        Updates all UI elements with appropriately scaled fonts.
        Also adjusts text wrapping width based on window size.
        """
        # Large font for main text
        self.text_display.config(
            font=("Helvetica", self.ui_state.font_size_large),
            wraplength=int(self.ui_state.window_width * UIConstants.TEXT_WRAP_RATIO)
        )

        # Medium font for labels
        self.label_display.config(
            font=("Helvetica", self.ui_state.font_size_medium)
        )

        # Small font for status and help
        small_font = ("Helvetica", self.ui_state.font_size_small)
        self.status_label.config(font=small_font)
        self.rec_indicator.config(font=("Helvetica", self.ui_state.font_size_small, "bold"))
        self.progress_label.config(font=small_font)
        self.help_label.config(font=small_font)

    def _on_window_resize(self, event: tk.Event) -> None:
        """Handle window resize events.

        Recalculates and applies font sizes when the window is resized
        to maintain correct text scaling.

        Args:
            event: Tkinter resize event
        """
        if event.widget == self.root:
            # Update window dimensions
            self.ui_state.window_width = event.width
            self.ui_state.window_height = event.height

            # Recalculate and apply fonts
            self._calculate_font_sizes()
            self._apply_fonts()

    def update_display(self, index: int, is_recording: bool) -> None:
        """Update the display with current utterance.

        Updates the main text display, label, progress counter, and
        recording indicator based on current state.

        Args:
            index: Current utterance index
            is_recording: Whether currently recording
        """
        if 0 <= index < len(self.recording_state.utterances):
            self.text_var.set(self.recording_state.utterances[index])
            self.label_var.set(f"{self.recording_state.labels[index]}:")
            self.progress_var.set(f"{index + 1}/{len(self.recording_state.utterances)}")

        # Update recording indicator
        if is_recording:
            self.text_display.config(fg=UIConstants.COLOR_TEXT_RECORDING)
            self.rec_indicator.config(fg=UIConstants.COLOR_TEXT_RECORDING)
            self.status_var.set("Recording...")
        else:
            self.text_display.config(fg=UIConstants.COLOR_TEXT_NORMAL)
            self.rec_indicator.config(fg=UIConstants.COLOR_TEXT_INACTIVE)
            self.status_var.set("Ready")

    def set_status(self, message: str) -> None:
        """Set status message.

        Args:
            message: Status text to display in the info bar
        """
        self.status_var.set(message)

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode.

        Switches between fullscreen and windowed modes, adjusting
        window dimensions and recalculating font sizes accordingly.
        """
        current = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current)

        if not current:
            self.ui_state.window_width = self.ui_state.screen_width
            self.ui_state.window_height = self.ui_state.screen_height
        else:
            self.ui_state.window_width = int(
                self.ui_state.screen_width * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )
            self.ui_state.window_height = int(
                self.ui_state.screen_height * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )

        self._on_window_resize(tk.Event())

    def toggle_spectrogram(self) -> None:
        """Toggle mel spectrogram visibility.

        Shows or hides the mel spectrogram widget in the control area.
        Updates UI state and displays a status message.
        """
        if hasattr(self, 'spec_frame') and self.spec_frame:
            if self.spec_frame.winfo_viewable():
                # Hide spectrogram
                self.spec_frame.pack_forget()
                self.ui_state.spectrogram_visible = False
                self.set_status("Mel spectrogram hidden")
            else:
                # Show spectrogram
                self.spec_frame.pack(
                    fill=tk.BOTH,
                    expand=True,
                    padx=UIConstants.FRAME_SPACING,
                    pady=(0, UIConstants.FRAME_SPACING),
                    before=self.help_label
                )
                self.spec_frame.pack_propagate(False)
                self.ui_state.spectrogram_visible = True
                self.set_status("Mel spectrogram shown")

                # Force redraw to avoid white display
                if hasattr(self, 'mel_spectrogram') and self.mel_spectrogram:
                    self.root.update_idletasks()
                    self.mel_spectrogram.canvas.draw_idle()

    def show_message(self, message: str, duration: int = 2000) -> None:
        """Show a temporary message.

        Displays a message in the main text area temporarily,
        then restores the normal display.

        Args:
            message: Message text to display
            duration: Display duration in milliseconds (default: 2000)
        """
        self.text_var.set(message)
        self.root.after(duration, self._restore_display)

    def _restore_display(self) -> None:
        """Restore normal display after temporary message.

        Called automatically after show_message() timeout to restore
        the current utterance display.
        """
        self.update_display(
            self.recording_state.current_index,
            self.recording_state.is_recording
        )

    def focus_window(self) -> None:
        """Bring window to front and focus.

        Ensures the window is visible and has keyboard focus.
        Uses platform-specific techniques for reliable focus,
        especially on macOS.
        """
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(UIConstants.FOCUS_DELAY_MS,
                       lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()

        # Platform-specific focus
        import platform
        if platform.system() == 'Darwin':  # macOS
            self.root.after(UIConstants.FOCUS_DELAY_MS,
                           lambda: self.root.focus_force())