"""Main window UI for the EmoSpeech Recorder."""

from typing import Optional, Callable
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ..constants import UIConstants, KeyBindings
from ..utils.config import UIConfig, RecorderConfig
from ..utils.state import UIState, RecordingState
from ..utils.settings_manager import SettingsManager
from .spectrogram import MelSpectrogramWidget
from .icon import AppIcon
from .info_overlay import InfoOverlay


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
                 shared_state: dict = None,
                 app_callbacks: dict = None,
                 settings_manager: Optional[SettingsManager] = None):
        """Initialize the main window.

        Args:
            root: Tkinter root window
            config: Application configuration with display and UI settings
            recording_state: Recording state manager tracking current utterance
            ui_state: UI state manager for window properties
            shared_state: Shared state dictionary
            app_callbacks: Application callbacks
            settings_manager: Settings manager for persisting preferences
        """
        self.root = root
        self.config = config
        self.recording_state = recording_state
        self.ui_state = ui_state
        self.shared_state = shared_state or {}
        self.app_callbacks = app_callbacks or {}
        self.settings_manager = settings_manager or SettingsManager()

        # Get screen information
        self._setup_screen_geometry()

        # Configure window
        self._setup_window()

        # Create menu bar
        self._create_menu()

        # Create UI elements
        self._create_ui()

        # Create info overlay
        self.info_overlay = InfoOverlay(self.root)

        # Show info overlay if enabled in settings
        if getattr(self.settings_manager.settings, 'show_info_overlay', False):
            self.info_overlay.visible = True
            # Update checkbox
            if hasattr(self, 'info_overlay_var'):
                self.info_overlay_var.set(True)
            # Show after window is ready
            self.root.after(100, lambda: self._show_info_overlay_on_startup())

        # Bind resize events
        self.root.bind('<Configure>', self._on_window_resize)

        # Force initial resize event after window is mapped
        self.root.after(50, self._trigger_initial_resize)

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
            # Try to restore saved geometry
            saved_geometry = self.settings_manager.settings.window_geometry
            if saved_geometry:
                self.root.geometry(saved_geometry)
                # Update state from saved geometry
                parts = saved_geometry.split('+')[0].split('x')
                self.ui_state.window_width = int(parts[0])
                self.ui_state.window_height = int(parts[1])
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

    def _create_menu(self) -> None:
        """Create the application menu bar.

        Creates a menu bar with File, View, and Help menus.
        """
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        # File menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Quit", command=self.root.quit, accelerator="Q")

        # View menu
        view_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="View", menu=view_menu)

        # Mel Spectrogram checkbutton
        self.mel_spectrogram_var = tk.BooleanVar(value=self.config.display.show_spectrogram)
        view_menu.add_checkbutton(
            label="Show Mel Spectrogram",
            variable=self.mel_spectrogram_var,
            command=self._toggle_mel_spectrogram_callback,
            accelerator="M"
        )

        # Info Overlay checkbutton
        self.info_overlay_var = tk.BooleanVar(value=getattr(self.settings_manager.settings, 'show_info_overlay', False))
        view_menu.add_checkbutton(
            label="Show Info Overlay",
            variable=self.info_overlay_var,
            command=self._toggle_info_overlay_callback,
            accelerator="I"
        )

        # Fullscreen checkbutton
        self.fullscreen_var = tk.BooleanVar(value=self.config.ui.fullscreen)
        view_menu.add_checkbutton(
            label="Fullscreen",
            variable=self.fullscreen_var,
            command=self._toggle_fullscreen_callback,
            accelerator="F10"
        )

        # Settings menu
        settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Settings", menu=settings_menu)

        # Audio settings submenu
        audio_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="Audio", menu=audio_menu)

        # Sample Rate submenu
        sample_rate_menu = tk.Menu(audio_menu, tearoff=0)
        audio_menu.add_cascade(label="Sample Rate", menu=sample_rate_menu)

        self.sample_rate_var = tk.IntVar(value=self.config.audio.sample_rate)
        for rate in [16000, 22050, 44100, 48000, 96000]:
            sample_rate_menu.add_radiobutton(
                label=f"{rate} Hz",
                variable=self.sample_rate_var,
                value=rate,
                command=lambda r=rate: self._on_sample_rate_change(r)
            )

        # Bit Depth submenu
        bit_depth_menu = tk.Menu(audio_menu, tearoff=0)
        audio_menu.add_cascade(label="Bit Depth", menu=bit_depth_menu)

        self.bit_depth_var = tk.IntVar(value=self.config.audio.bit_depth)
        for depth in [16, 24]:
            bit_depth_menu.add_radiobutton(
                label=f"{depth} bit",
                variable=self.bit_depth_var,
                value=depth,
                command=lambda d=depth: self._on_bit_depth_change(d)
            )

        # Help menu
        help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_keyboard_shortcuts, accelerator="H")
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _show_keyboard_shortcuts(self) -> None:
        """Show keyboard shortcuts in a dialog window."""
        shortcuts_window = tk.Toplevel(self.root)
        shortcuts_window.title("Keyboard Shortcuts")
        shortcuts_window.geometry("800x600")
        shortcuts_window.resizable(False, False)

        # Create text widget with shortcuts
        text = tk.Text(shortcuts_window, wrap=tk.WORD, padx=30, pady=30,
                      bg=UIConstants.COLOR_BACKGROUND,
                      fg=UIConstants.COLOR_TEXT_NORMAL,
                      font=('TkDefaultFont', 14))
        text.pack(fill=tk.BOTH, expand=True)

        # Add shortcuts text
        shortcuts_text = """
RECORDING CONTROLS:
  SPACE    Start/Stop Recording
  P        Play Current Recording
  D        Delete Current Recording

NAVIGATION:
  ↑/↓      Navigate Previous/Next Utterance
  ←/→      Browse Takes (Previous/Next)

DISPLAY:
  M        Toggle Mel Spectrogram
  F10      Toggle Fullscreen
  I        Show Audio Info Overlay

GENERAL:
  H        Show Keyboard Shortcuts (this window)
  Q        Quit Application
"""
        text.insert('1.0', shortcuts_text)
        text.config(state=tk.DISABLED)  # Make read-only

        # Add close button
        close_btn = tk.Button(shortcuts_window, text="Close",
                            command=shortcuts_window.destroy)
        close_btn.pack(pady=10)

        # Focus the window
        shortcuts_window.focus_set()

    def _show_about(self) -> None:
        """Show about dialog."""
        about_window = tk.Toplevel(self.root)
        about_window.title("About EmoSpeech Recorder")
        about_window.geometry("400x200")
        about_window.resizable(False, False)

        about_text = """EmoSpeech Recorder

A professional tool for recording emotional speech datasets.

Used to create Talrómur 3, the Icelandic emotional speech dataset."""

        label = tk.Label(about_window, text=about_text, justify=tk.CENTER,
                        padx=20, pady=20)
        label.pack(fill=tk.BOTH, expand=True)

        close_btn = tk.Button(about_window, text="Close",
                            command=about_window.destroy)
        close_btn.pack(pady=10)

        about_window.focus_set()

    def _toggle_mel_spectrogram_callback(self) -> None:
        """Callback for menu toggle mel spectrogram."""
        # Use app callback if available, otherwise just toggle locally
        if 'toggle_mel_spectrogram' in self.app_callbacks:
            self.app_callbacks['toggle_mel_spectrogram']()
        else:
            self.toggle_spectrogram()

    def _toggle_info_overlay_callback(self) -> None:
        """Callback for menu toggle info overlay."""
        # Toggle info overlay
        self.info_overlay.toggle()
        # Update settings
        self.settings_manager.update_setting('show_info_overlay', self.info_overlay.visible)

        # If now visible, show content after small delay to ensure frame is placed
        if self.info_overlay.visible:
            # Update checkbox
            if hasattr(self, 'info_overlay_var'):
                self.info_overlay_var.set(True)
            # Call app callback after delay
            if 'update_info_overlay' in self.app_callbacks:
                self.root.after(10, self.app_callbacks['update_info_overlay'])
        else:
            # Update checkbox
            if hasattr(self, 'info_overlay_var'):
                self.info_overlay_var.set(False)

    def _toggle_fullscreen_callback(self) -> None:
        """Callback for menu toggle fullscreen."""
        self.toggle_fullscreen()

    def _on_sample_rate_change(self, rate: int) -> None:
        """Handle sample rate change from menu.

        Args:
            rate: New sample rate in Hz
        """
        self.config.audio.sample_rate = rate
        self.settings_manager.update_setting('sample_rate', rate)

        # Notify app if callback available
        if 'update_audio_settings' in self.app_callbacks:
            self.app_callbacks['update_audio_settings']()

        self.set_status(f"Sample rate changed to {rate} Hz")

    def _on_bit_depth_change(self, depth: int) -> None:
        """Handle bit depth change from menu.

        Args:
            depth: New bit depth (16 or 24)
        """
        self.config.audio.bit_depth = depth
        self.config.audio.__post_init__()  # Update dtype and subtype
        self.settings_manager.update_setting('bit_depth', depth)

        # Notify app if callback available
        if 'update_audio_settings' in self.app_callbacks:
            self.app_callbacks['update_audio_settings']()

        self.set_status(f"Bit depth changed to {depth} bit")

    def _set_window_icon(self) -> None:
        """Set the window icon.

        Creates a custom microphone icon for the application window.
        Falls back to a simple icon if the detailed one fails.
        """
        try:
            # Try to create the icon
            icon_path = Path(__file__).parent.parent / "resources" / "microphone.png"
            icon = AppIcon.create_icon(icon_path)
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

        # Force update of all widgets
        self.root.update_idletasks()

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

        # Always create spectrogram widget, but hide if not enabled
        self._create_spectrogram_widget()

        # Hide if not enabled in settings
        if not self.config.display.show_spectrogram:
            self.spec_frame.pack_forget()
            self.ui_state.spectrogram_visible = False


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

            # Update info overlay position if it exists
            if hasattr(self, 'info_overlay'):
                self.info_overlay.update_position()

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
        Saves window position before going fullscreen and restores
        it when exiting fullscreen.
        """
        current = self.root.attributes('-fullscreen')

        if not current:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

        # Update menu checkbutton
        if hasattr(self, 'fullscreen_var'):
            self.fullscreen_var.set(not current)

        # Save preference
        self.settings_manager.update_setting('fullscreen', not current)

    def _enter_fullscreen(self) -> None:
        """Enter fullscreen mode.

        Saves current window geometry and switches to fullscreen.
        """
        # Save current geometry
        self.ui_state.saved_window_geometry = self.root.geometry()

        # Enter fullscreen
        self.root.attributes('-fullscreen', True)

        # Update window dimensions
        self.ui_state.window_width = self.ui_state.screen_width
        self.ui_state.window_height = self.ui_state.screen_height

        # Trigger resize event
        self._trigger_resize_event()

    def _exit_fullscreen(self) -> None:
        """Exit fullscreen mode.

        Restores saved window geometry or applies default positioning.
        Uses withdraw/deiconify to prevent visual artifacts.
        """
        # Hide window during transition to prevent black window flash
        self.root.withdraw()

        # Exit fullscreen
        self.root.attributes('-fullscreen', False)

        # Restore geometry
        self._restore_window_geometry()

        # Force window update and show window again
        self.root.update_idletasks()
        self.root.deiconify()

        # Trigger resize event
        self._trigger_resize_event()

    def _restore_window_geometry(self) -> None:
        """Restore window geometry after exiting fullscreen.

        Uses saved geometry if available, otherwise centers window
        with default dimensions.
        """
        if self.ui_state.saved_window_geometry:
            # Restore saved position and size
            self.root.geometry(self.ui_state.saved_window_geometry)
            # Update window dimensions from saved geometry
            parts = self.ui_state.saved_window_geometry.split('+')[0].split('x')
            self.ui_state.window_width = int(parts[0])
            self.ui_state.window_height = int(parts[1])
        else:
            # Fallback to default size centered
            self.ui_state.window_width = int(
                self.ui_state.screen_width * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )
            self.ui_state.window_height = int(
                self.ui_state.screen_height * UIConstants.DEFAULT_WINDOW_SIZE_RATIO
            )
            # Center window
            x = (self.ui_state.screen_width - self.ui_state.window_width) // 2
            y = (self.ui_state.screen_height - self.ui_state.window_height) // 2
            self.root.geometry(f"{self.ui_state.window_width}x{self.ui_state.window_height}+{x}+{y}")

    def _trigger_resize_event(self) -> None:
        """Trigger a resize event to update fonts and layout."""
        event = tk.Event()
        event.widget = self.root
        event.width = self.ui_state.window_width
        event.height = self.ui_state.window_height
        self._on_window_resize(event)

    def _trigger_initial_resize(self) -> None:
        """Trigger initial resize after window is fully mapped."""
        # Update window dimensions from actual window
        self.root.update_idletasks()
        self.ui_state.window_width = self.root.winfo_width()
        self.ui_state.window_height = self.root.winfo_height()
        # Trigger resize event
        self._trigger_resize_event()

    def toggle_spectrogram(self, update_external_state: Optional[Callable] = None) -> None:
        """Toggle mel spectrogram visibility.

        Shows or hides the mel spectrogram widget in the control area.
        Updates UI state and displays a status message.

        Args:
            update_external_state: Optional callback to update external state
        """
        if hasattr(self, 'spec_frame') and self.spec_frame:
            if self.spec_frame.winfo_viewable():
                # Hide spectrogram
                self.spec_frame.pack_forget()
                self.ui_state.spectrogram_visible = False
            else:
                # Show spectrogram
                self.spec_frame.pack(
                    fill=tk.BOTH,
                    expand=True,
                    padx=UIConstants.FRAME_SPACING,
                    pady=(0, UIConstants.FRAME_SPACING)
                )
                self.spec_frame.pack_propagate(False)
                self.ui_state.spectrogram_visible = True

                # Force redraw to avoid white display
                if hasattr(self, 'mel_spectrogram') and self.mel_spectrogram:
                    self.root.update_idletasks()
                    self.mel_spectrogram.canvas.draw_idle()

        # Update menu checkbutton
        if hasattr(self, 'mel_spectrogram_var'):
            self.mel_spectrogram_var.set(self.ui_state.spectrogram_visible)

        # Call external state update if provided
        if update_external_state:
            update_external_state()

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

    def show_info_overlay(self, file_path: Optional[Path] = None,
                         is_recording: bool = False,
                         recording_params: Optional[dict] = None) -> None:
        """Show or toggle the info overlay.

        Args:
            file_path: Path to audio file
            is_recording: Whether currently recording
            recording_params: Recording parameters dict
        """
        # Toggle visibility
        self.info_overlay.toggle()

        # If now visible, show with parameters after small delay
        if self.info_overlay.visible:
            self.root.after(10, lambda: self.info_overlay.show(file_path, is_recording, recording_params))

    def _show_info_overlay_on_startup(self) -> None:
        """Show info overlay on startup with current state."""
        # Call app's update_info_overlay if available
        if 'update_info_overlay' in self.app_callbacks:
            self.app_callbacks['update_info_overlay']()