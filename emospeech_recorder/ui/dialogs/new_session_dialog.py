"""New Session Dialog for creating recording sessions."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

from ...utils.device_manager import get_device_manager


class NewSessionConstants:
    """Constants for the New Session Dialog."""

    EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "helpful"]
    GENDER_OPTIONS = [("Male", "M"), ("Female", "F"), ("Other", "X")]
    RECORDING_FORMATS = [("FLAC (lossless)", "flac"), ("WAV (uncompressed)", "wav")]
    DEFAULT_FORMAT = "flac"
    MIN_WIDTH = 550
    MIN_HEIGHT = 400
    DEFAULT_HEIGHT = 550
    PADDING = {
        "label_column": 120,
        "browse_button": 80,
        "entry_borders": 20,
        "dialog_margins": 40,
    }


@dataclass
class NewSessionData:
    """Data collected from the new session dialog."""

    speaker_name: str
    gender: str
    emotion: str
    script_path: Path
    base_dir: Path
    input_device: Optional[str]  # Device name, not index
    sample_rate: int
    bit_depth: int
    recording_format: str
    custom_dir_name: Optional[str] = None


class NewSessionDialog:
    """Dialog for creating a new recording session."""

    def __init__(
        self,
        parent: tk.Tk,
        default_base_dir: Path,
        current_sample_rate: int,
        current_bit_depth: int,
        current_input_device: Optional[str] = None,
    ):
        """Initialize the new session dialog.

        Args:
            parent: Parent window
            default_base_dir: Default directory for sessions
            current_sample_rate: Current sample rate in Hz from app config
            current_bit_depth: Current bit depth (16 or 24) from app config
            current_input_device: Current input device name from app config
        """
        self.parent = parent
        self.result: Optional[NewSessionData] = None
        self.default_base_dir = default_base_dir
        self.current_sample_rate = current_sample_rate
        self.current_bit_depth = current_bit_depth
        self.current_input_device_name = current_input_device

        # Get device manager
        self.device_manager = get_device_manager()

        # Get available input devices
        self.input_devices = self.device_manager.get_input_devices()

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("New Session")

        # Hide window initially to prevent flashing
        self.dialog.withdraw()

        # Set as modal dialog
        self.dialog.transient(parent)

        # Make dialog resizable but set minimum size
        self.dialog.minsize(
            NewSessionConstants.MIN_WIDTH, NewSessionConstants.MIN_HEIGHT
        )

        # Initialize all variables and data
        self._initialize_variables()
        self._initialize_device_data()

        # Create UI
        self._create_widgets()

        # Calculate optimal width and center the dialog
        self._calculate_optimal_width()

        # Show the dialog now that it's positioned
        self.dialog.deiconify()

        # Grab focus after showing
        self.dialog.grab_set()

        # Focus on first input
        self.speaker_entry.focus_set()

        # Setup keyboard bindings
        self._setup_keyboard_bindings()

    def _calculate_optimal_width(self):
        """Calculate optimal dialog width based on font metrics and path length."""
        # Get the default font used by ttk.Entry
        entry_font = font.nametofont("TkDefaultFont")

        # Measure the pixel width of the base directory path
        path_text = str(self.default_base_dir)
        text_width = entry_font.measure(path_text)

        # Add padding for UI elements
        padding = NewSessionConstants.PADDING
        total_width = (
            text_width
            + padding["label_column"]
            + padding["browse_button"]
            + padding["entry_borders"]
            + padding["dialog_margins"]
        )

        # Constrain to reasonable limits
        optimal_width = max(NewSessionConstants.MIN_WIDTH, min(900, total_width))

        # Set the dialog geometry
        self.dialog.geometry(f"{optimal_width}x{NewSessionConstants.DEFAULT_HEIGHT}")

        # Center after setting size
        self.dialog.update_idletasks()
        self._center_window()

    def _center_window(self):
        """Center the dialog on the parent window."""
        self.dialog.update_idletasks()

        # Get parent position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        # Get dialog size
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()

        # Calculate center position
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2

        self.dialog.geometry(f"+{x}+{y}")

    def _initialize_variables(self):
        """Initialize all dialog variables."""
        # Session variables
        self.speaker_name_var = tk.StringVar()
        self.gender_var = tk.StringVar(value="M")
        self.emotion_var = tk.StringVar(value="neutral")
        self.script_path_var = tk.StringVar()
        self.base_dir_var = tk.StringVar(value=str(self.default_base_dir))
        self.custom_dir_var = tk.StringVar()

        # Audio settings variables
        self.selected_device_name = tk.StringVar(
            value=self.current_input_device_name or "System Default"
        )
        self.sample_rate_var = tk.IntVar(value=self.current_sample_rate)
        self.bit_depth_var = tk.IntVar(value=self.current_bit_depth)
        self.recording_format_var = tk.StringVar(
            value=NewSessionConstants.DEFAULT_FORMAT
        )

        # Store available rates and depths for current device
        self.available_sample_rates: List[int] = []
        self.available_bit_depths: List[int] = []

    def _initialize_device_data(self):
        """Initialize device-related data structures."""
        # Build device lists for display
        self.device_names = ["System Default"]
        self.device_display_names = ["System Default"]

        for dev in self.input_devices:
            self.device_names.append(dev["name"])
            self.device_display_names.append(
                f"{dev['name']} (Ch: {dev['max_input_channels']})"
            )

    def _setup_keyboard_bindings(self):
        """Setup keyboard shortcuts for the dialog."""
        self.dialog.bind("<Return>", lambda e: self._on_ok())
        self.dialog.bind("<Escape>", lambda e: self._on_cancel())

    def _create_main_frame(self) -> ttk.Frame:
        """Create and configure the main frame."""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.grid(row=0, column=0, sticky="wens")

        # Configure grid weights
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        return main_frame

    def _create_widgets(self):
        """Create and layout dialog widgets."""
        self.main_frame = self._create_main_frame()

        row = 0
        row = self._create_speaker_section(self.main_frame, row)
        row = self._create_file_section(self.main_frame, row)
        row = self._add_separator(self.main_frame, row)
        row = self._create_audio_section(self.main_frame, row)
        row = self._create_info_section(self.main_frame, row)
        row = self._add_separator(self.main_frame, row)
        self._create_button_section(self.main_frame, row)

        # Initialize audio settings after all widgets are created
        self._update_audio_settings()

    @staticmethod
    def _add_separator(parent: ttk.Frame, row: int) -> int:
        """Add a horizontal separator."""
        row += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="we", pady=(10, 5)
        )
        return row

    def _create_speaker_section(self, parent: ttk.Frame, row: int) -> int:
        """Create speaker information section."""
        # Speaker Name
        row = self._create_labeled_entry(
            parent, row, "Speaker Name:*", self.speaker_name_var, required=True
        )
        self.speaker_entry = parent.grid_slaves(row=row - 1, column=1)[0]

        # Gender
        row = self._create_gender_field(parent, row)

        # Emotion
        row = self._create_emotion_field(parent, row)

        return row

    @staticmethod
    def _create_labeled_entry(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        required: bool = False,
        readonly: bool = False,
    ) -> int:
        """Create a labeled entry field."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=5)
        entry = ttk.Entry(parent, textvariable=variable)
        if readonly:
            entry.configure(state="readonly")
        entry.grid(row=row, column=1, sticky="we", pady=5)
        return row + 1

    def _create_gender_field(self, parent: ttk.Frame, row: int) -> int:
        """Create gender selection field."""
        ttk.Label(parent, text="Gender:*").grid(row=row, column=0, sticky=tk.W, pady=5)

        gender_frame = ttk.Frame(parent)
        gender_frame.grid(row=row, column=1, sticky=tk.W, pady=5)

        for text, value in NewSessionConstants.GENDER_OPTIONS:
            ttk.Radiobutton(
                gender_frame, text=text, variable=self.gender_var, value=value
            ).pack(side=tk.LEFT, padx=(0, 10))

        return row + 1

    def _create_emotion_field(self, parent: ttk.Frame, row: int) -> int:
        """Create emotion selection field."""
        ttk.Label(parent, text="Emotion:*").grid(row=row, column=0, sticky=tk.W, pady=5)

        emotion_combo = ttk.Combobox(
            parent,
            textvariable=self.emotion_var,
            values=NewSessionConstants.EMOTIONS,
            state="readonly",
            width=20,
        )
        emotion_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        return row + 1

    def _create_file_section(self, parent: ttk.Frame, row: int) -> int:
        """Create file selection section."""
        # Script File
        row = self._create_browse_field(
            parent,
            row,
            "Script File:*",
            self.script_path_var,
            self._browse_script,
            required=True,
        )

        # Base Directory
        row = self._create_browse_field(
            parent, row, "Base Directory:", self.base_dir_var, self._browse_base_dir
        )

        # Custom Directory
        row = self._create_labeled_entry(
            parent, row, "Session Directory:", self.custom_dir_var
        )

        return row

    @staticmethod
    def _create_browse_field(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        command: callable,
        required: bool = False,
    ) -> int:
        """Create a field with browse button."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=5)

        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="we", pady=5)
        frame.columnconfigure(0, weight=1)

        ttk.Entry(frame, textvariable=variable, state="readonly").grid(
            row=0, column=0, sticky="we"
        )
        ttk.Button(frame, text="Browse...", command=command).grid(
            row=0, column=1, padx=(5, 0)
        )

        return row + 1

    def _create_audio_section(self, parent: ttk.Frame, row: int) -> int:
        """Create audio settings section."""
        # Section header
        row += 1
        audio_label = ttk.Label(
            parent,
            text="Audio Settings (locked after session creation)",
            font=("TkDefaultFont", 0, "bold"),
        )
        audio_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(5, 10))

        # Input Device
        row += 1
        row = self._create_device_field(parent, row)

        # Audio settings
        row = self._create_sample_rate_field(parent, row)
        row = self._create_bit_depth_field(parent, row)
        row = self._create_format_field(parent, row)
        return row

    def _create_device_field(self, parent: ttk.Frame, row: int) -> int:
        """Create input device selection field."""
        ttk.Label(parent, text="Input Device:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        self.device_combo = ttk.Combobox(
            parent, values=self.device_display_names, state="readonly", width=40
        )
        self.device_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        # Set initial device
        if (
            self.current_input_device_name
            and self.current_input_device_name in self.device_names
        ):
            idx = self.device_names.index(self.current_input_device_name)
            self.device_combo.current(idx)
        else:
            self.device_combo.current(0)  # System default

        # Bind device change event
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)

        return row + 1

    def _create_sample_rate_field(self, parent: ttk.Frame, row: int) -> int:
        """Create sample rate selection field."""
        ttk.Label(parent, text="Sample Rate:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        self.sample_rate_combo = ttk.Combobox(parent, state="readonly", width=15)
        self.sample_rate_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        # Bind the event
        self.sample_rate_combo.bind("<<ComboboxSelected>>", self._on_sample_rate_change)

        return row + 1

    def _create_bit_depth_field(self, parent: ttk.Frame, row: int) -> int:
        """Create bit depth selection field."""
        ttk.Label(parent, text="Bit Depth:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        self.bit_depth_frame = ttk.Frame(parent)
        self.bit_depth_frame.grid(row=row, column=1, sticky=tk.W, pady=5)

        # Radio buttons will be created dynamically based on device
        self.bit_16_radio = None
        self.bit_24_radio = None

        return row + 1

    def _create_format_field(self, parent: ttk.Frame, row: int) -> int:
        """Create recording format selection field."""
        ttk.Label(parent, text="Recording Format:").grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        format_frame = ttk.Frame(parent)
        format_frame.grid(row=row, column=1, sticky=tk.W, pady=5)

        for text, value in NewSessionConstants.RECORDING_FORMATS:
            ttk.Radiobutton(
                format_frame, text=text, variable=self.recording_format_var, value=value
            ).pack(side=tk.LEFT, padx=(0, 15))

        return row + 1

    @staticmethod
    def _create_info_section(parent: ttk.Frame, row: int) -> int:
        """Create info section with help text."""
        row += 1
        info_frame = ttk.Frame(parent)
        info_frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=10)
        info_frame.columnconfigure(0, weight=1)

        info_text = "* Required fields\n\n"
        info_text += "If Session Directory is empty, a name will be\n"
        info_text += "generated from speaker and emotion."
        info_label = ttk.Label(
            info_frame, text=info_text, foreground="gray", justify=tk.RIGHT
        )
        info_label.grid(row=0, column=0, sticky=tk.E)

        return row

    def _create_button_section(self, parent: ttk.Frame, row: int) -> None:
        """Create OK/Cancel button section."""
        row += 1
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=2, sticky=tk.E)

        ttk.Button(
            button_frame, text="OK", command=self._on_ok, default=tk.ACTIVE
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(
            side=tk.LEFT
        )

    def _browse_script(self):
        """Browse for a script file."""
        filename = filedialog.askopenfilename(
            parent=self.dialog,
            title="Select Script File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(self.default_base_dir),
        )
        if filename:
            self.script_path_var.set(filename)

    def _browse_base_dir(self):
        """Browse for base directory."""
        dirname = filedialog.askdirectory(
            parent=self.dialog,
            title="Select Base Directory",
            initialdir=str(self.base_dir_var.get() or self.default_base_dir),
        )
        if dirname:
            self.base_dir_var.set(dirname)

    def _on_device_change(self, event=None):
        """Handle input device selection change."""
        self._update_audio_settings()

    def _on_sample_rate_change(self, event=None):
        """Handle sample rate selection change."""
        selected = self.sample_rate_combo.get()
        if selected:
            numeric_value = int(selected.split()[0])
            self.sample_rate_var.set(numeric_value)
            # Update bit depths for the new sample rate
            self._update_bit_depths()

    def _update_audio_settings(self):
        """Update available sample rates and bit depths based on selected device."""
        # Get selected device
        selected_idx = (
            self.device_combo.current() if hasattr(self, "device_combo") else 0
        )
        device_name = self.device_names[selected_idx] if selected_idx > 0 else None

        # Get supported rates for the device
        self.available_sample_rates = self.device_manager.get_supported_sample_rates(
            device_name
        )

        # Update sample rate dropdown
        if hasattr(self, "sample_rate_combo"):
            sample_rate_strings = [f"{rate} Hz" for rate in self.available_sample_rates]
            self.sample_rate_combo["values"] = sample_rate_strings

            # Try to keep current selection if still available
            if self.sample_rate_var.get() in self.available_sample_rates:
                self.sample_rate_combo.set(f"{self.sample_rate_var.get()} Hz")
            elif self.current_sample_rate in self.available_sample_rates:
                self.sample_rate_combo.set(f"{self.current_sample_rate} Hz")
                self.sample_rate_var.set(self.current_sample_rate)
            elif 48000 in self.available_sample_rates:
                self.sample_rate_combo.set("48000 Hz")
                self.sample_rate_var.set(48000)
            elif self.available_sample_rates:
                # Use the first available rate
                self.sample_rate_combo.set(f"{self.available_sample_rates[0]} Hz")
                self.sample_rate_var.set(self.available_sample_rates[0])

        # Update bit depths for the selected sample rate
        self._update_bit_depths()

    def _update_bit_depths(self):
        """Update available bit depths based on selected device and sample rate."""
        # Get selected device
        selected_idx = (
            self.device_combo.current() if hasattr(self, "device_combo") else 0
        )
        device_name = self.device_names[selected_idx] if selected_idx > 0 else None

        # Get current sample rate
        current_sample_rate = self.sample_rate_var.get()

        # Get supported bit depths for the device and sample rate
        self.available_bit_depths = self.device_manager.get_supported_bit_depths(
            device_name, current_sample_rate
        )

        # Update bit depth radio buttons
        if hasattr(self, "bit_depth_frame"):
            # Clear existing radio buttons
            for widget in self.bit_depth_frame.winfo_children():
                widget.destroy()

            # Create new radio buttons based on available depths
            if 16 in self.available_bit_depths:
                self.bit_16_radio = ttk.Radiobutton(
                    self.bit_depth_frame,
                    text="16 bit",
                    variable=self.bit_depth_var,
                    value=16,
                )
                self.bit_16_radio.pack(side=tk.LEFT, padx=(0, 10))

            if 24 in self.available_bit_depths:
                self.bit_24_radio = ttk.Radiobutton(
                    self.bit_depth_frame,
                    text="24 bit",
                    variable=self.bit_depth_var,
                    value=24,
                )
                self.bit_24_radio.pack(side=tk.LEFT)

            # Set appropriate default if current selection not available
            if self.bit_depth_var.get() not in self.available_bit_depths:
                if 24 in self.available_bit_depths:
                    self.bit_depth_var.set(24)
                elif 16 in self.available_bit_depths:
                    self.bit_depth_var.set(16)

    def _validate_input(self) -> bool:
        """Validate user input.

        Returns:
            bool: True if input is valid
        """
        errors = []

        if not self.speaker_name_var.get().strip():
            errors.append("Speaker name is required")

        if not self.script_path_var.get():
            errors.append("Script file is required")
        elif not Path(self.script_path_var.get()).exists():
            errors.append("Script file does not exist")

        if not self.base_dir_var.get():
            errors.append("Base directory is required")
        elif not Path(self.base_dir_var.get()).exists():
            errors.append("Base directory does not exist")

        if errors:
            messagebox.showerror(
                "Validation Error", "\n".join(errors), parent=self.dialog
            )
            return False

        return True

    def _on_ok(self):
        """Handle OK button."""
        if not self._validate_input():
            return

        # Get selected device name
        selected_device_idx = self.device_combo.current()
        device_name = "default"  # Default to system default
        if selected_device_idx > 0:  # Not "System Default"
            device_name = self.device_names[selected_device_idx]

        # Create result, save it and exit
        self.result = NewSessionData(
            speaker_name=self.speaker_name_var.get().strip(),
            gender=self.gender_var.get(),
            emotion=self.emotion_var.get(),
            script_path=Path(self.script_path_var.get()),
            base_dir=Path(self.base_dir_var.get()),
            input_device=device_name,  # Store device name or "default"
            sample_rate=self.sample_rate_var.get(),
            bit_depth=self.bit_depth_var.get(),
            recording_format=self.recording_format_var.get(),
            custom_dir_name=self.custom_dir_var.get().strip() or None,
        )
        self.dialog.destroy()

    def _on_cancel(self):
        """Handle Cancel button."""
        self.result = None
        self.dialog.destroy()

    def show(self) -> Optional[NewSessionData]:
        """Show the dialog and return the result.

        Returns:
            NewSessionData if OK was clicked, None if cancelled
        """
        self.dialog.wait_window()
        return self.result
