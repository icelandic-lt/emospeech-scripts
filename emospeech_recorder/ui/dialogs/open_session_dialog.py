"""Open Session Dialog for loading existing sessions."""

import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional


class OpenSessionDialog:
    """Dialog for opening existing recording sessions.

    This is a placeholder implementation that will be completed
    in Phase 3, Commit 9.
    """

    def __init__(self, parent: tk.Tk, default_base_dir: Path = None):
        """Initialize the open session dialog.

        Args:
            parent: Parent window
            default_base_dir: Default directory for sessions
        """
        self.parent = parent
        self.result: Optional[Path] = None
        self.default_base_dir = default_base_dir or Path.home()

    def show(self) -> Optional[Path]:
        """Show the dialog and return the selected session path.

        Returns:
            Path to selected session directory or None if cancelled
        """
        # For now, just use a simple directory dialog
        session_dir = filedialog.askdirectory(
            parent=self.parent,
            title="Select Session Directory (.revoxx)",
            initialdir=str(self.default_base_dir),
        )

        if session_dir:
            session_path = Path(session_dir)
            if session_path.name.endswith(".revoxx"):
                return session_path
            else:
                messagebox.showerror(
                    "Invalid Session",
                    "Please select a .revoxx directory",
                    parent=self.parent,
                )
                return None

        return None
