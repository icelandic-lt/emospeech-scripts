"""Session Settings Dialog for viewing current session configuration."""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional
from datetime import datetime

from ...session import Session


class SessionSettingsDialog:
    """Dialog for viewing current session settings (read-only)."""

    def __init__(self, parent: tk.Tk, session: Session):
        """Initialize the session settings dialog.

        Args:
            parent: Parent window
            session: Current session to display
        """
        self.parent = parent
        self.session = session

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Session Settings")

        # Set a fixed size that should fit all content
        self.dialog.geometry("450x600")
        self.dialog.resizable(False, False)

        # Hide window initially (to prevent flashing)
        self.dialog.withdraw()

        # Set as modal dialog
        self.dialog.transient(parent)

        # Create UI
        self._create_widgets()

        # Center the window before showing
        self._center_window()

        # Now show the window at the correct position
        self.dialog.deiconify()

        # Grab focus after showing
        self.dialog.grab_set()

        # Setup keyboard bindings
        self.dialog.bind("<Escape>", lambda e: self._on_close())
        self.dialog.bind("<Return>", lambda e: self._on_close())

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

        # Ensure dialog stays on screen
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()

        # Adjust if necessary
        x = max(10, min(x, screen_width - dialog_width - 10))
        y = max(10, min(y, screen_height - dialog_height - 50))

        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create and layout dialog widgets."""
        # Main frame with padding
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid weights for stretching
        main_frame.columnconfigure(1, weight=1)

        row = 0

        # Session Information Section
        row = self._add_section_header(main_frame, row, "Session Information")
        row = self._add_field(
            main_frame,
            row,
            "Session Name:",
            self.session.name if self.session.name else "Unnamed Session",
        )
        row = self._add_field(
            main_frame,
            row,
            "Session Directory:",
            self.session.session_dir.name if self.session.session_dir else "N/A",
        )

        # Add creation date if available
        if self.session.created_at:
            created_str = self.session.created_at.strftime("%Y-%m-%d %H:%M")
            row = self._add_field(main_frame, row, "Created:", created_str)

        # Add separator
        row = self._add_separator(main_frame, row)

        # Speaker Information Section
        if self.session.speaker:
            row = self._add_section_header(main_frame, row, "Speaker Information")
            row = self._add_field(
                main_frame, row, "Speaker Name:", self.session.speaker.name
            )
            row = self._add_field(
                main_frame,
                row,
                "Gender:",
                self._format_gender(self.session.speaker.gender),
            )
            row = self._add_field(
                main_frame, row, "Emotion:", self.session.speaker.emotion.title()
            )
            row = self._add_separator(main_frame, row)

        # Audio Configuration Section
        if self.session.audio_config:
            row = self._add_section_header(main_frame, row, "Audio Configuration")

            # Format device name
            device_name = self.session.audio_config.input_device
            if device_name == "default" or device_name is None:
                device_display = "System Default"
            else:
                device_display = device_name

            row = self._add_field(main_frame, row, "Input Device:", device_display)
            row = self._add_field(
                main_frame,
                row,
                "Sample Rate:",
                f"{self.session.audio_config.sample_rate:,} Hz",
            )
            row = self._add_field(
                main_frame,
                row,
                "Bit Depth:",
                f"{self.session.audio_config.bit_depth} bit",
            )
            row = self._add_field(
                main_frame,
                row,
                "Channels:",
                (
                    f"{self.session.audio_config.channels} (Mono)"
                    if self.session.audio_config.channels == 1
                    else f"{self.session.audio_config.channels}"
                ),
            )
            row = self._add_field(
                main_frame, row, "Format:", self.session.audio_config.format.upper()
            )
            row = self._add_separator(main_frame, row)

        # Script Information Section
        row = self._add_section_header(main_frame, row, "Script Information")
        script_path = self.session.get_script_path()
        if script_path and script_path.exists():
            row = self._add_field(main_frame, row, "Script File:", script_path.name)

            # Count utterances if possible
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
                    utterance_count = len(lines)
                    row = self._add_field(
                        main_frame, row, "Total Utterances:", str(utterance_count)
                    )
            except:
                pass
        else:
            row = self._add_field(main_frame, row, "Script File:", "Not found")

        # Add some spacing before the button
        row += 1

        # Close button
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))

        ttk.Button(
            button_frame, text="Close", command=self._on_close, default=tk.ACTIVE
        ).pack(side=tk.RIGHT)

    def _add_section_header(self, parent: ttk.Frame, row: int, text: str) -> int:
        """Add a section header."""
        label = ttk.Label(parent, text=text, font=("TkDefaultFont", 0, "bold"))
        label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(8, 5))
        return row + 1

    @staticmethod
    def _add_field(parent: ttk.Frame, row: int, label: str, value: str) -> int:
        """Add a labeled field."""
        # Label for the field name
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky=tk.W, padx=(20, 10), pady=3
        )

        # Label for the value (instead of Entry)
        value_label = ttk.Label(parent, text=value, foreground="#333333")
        value_label.grid(row=row, column=1, sticky=tk.W, pady=3)

        return row + 1

    @staticmethod
    def _add_separator(parent: ttk.Frame, row: int) -> int:
        """Add a horizontal separator."""
        row += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="we", pady=5
        )
        return row + 1

    @staticmethod
    def _format_gender(gender: str) -> str:
        """Format gender code for display."""
        gender_map = {"M": "Male", "F": "Female", "X": "Other"}
        return gender_map.get(gender, gender)

    def _on_close(self):
        """Handle close button."""
        self.dialog.destroy()

    def show(self):
        """Show the dialog."""
        self.dialog.wait_window()
