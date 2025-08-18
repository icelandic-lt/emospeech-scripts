"""Application icon creation for Revoxx."""

import tkinter as tk
from typing import Optional
from pathlib import Path


class AppIcon:
    """Creates and manages the application icon.

    This class loads a PNG icon for use as the window icon.
    """

    @staticmethod
    def create_icon(icon_path: Path) -> Optional[tk.PhotoImage]:
        """Create icon from PNG file.

        Args:
            icon_path: Path to the PNG icon file

        Returns:
            PhotoImage object or None if creation fails
        """
        try:
            if not icon_path.exists():
                print(f"Icon file not found: {icon_path}")
                return None

            # Simply load and return the PNG at original size
            # macOS can handle large icons and will scale them as needed
            img = tk.PhotoImage(file=str(icon_path))

            if icon_path.parent.name == "debug":
                print(f"Loaded icon: {img.width()}x{img.height()} pixels")

            return img

        except Exception as e:
            print(f"Error creating icon from PNG: {e}")
            return None
