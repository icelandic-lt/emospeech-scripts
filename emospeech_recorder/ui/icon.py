"""Application icon creation for EmoSpeech Recorder."""

import tkinter as tk
from typing import Optional, Tuple
import os
from pathlib import Path


class AppIcon:
    """Creates and manages the application icon.

    This class loads and processes a PNG microphone icon
    for use as the window icon.
    """

    @staticmethod
    def find_content_bounds(img: tk.PhotoImage) -> Tuple[int, int, int, int]:
        """Find the bounds of non-transparent content in an image.

        Args:
            img: PhotoImage to analyze

        Returns:
            Tuple of (left, top, right, bottom) bounds
        """
        width = img.width()
        height = img.height()

        # Find bounds by checking for non-transparent pixels
        left, top, right, bottom = width, height, 0, 0

        # Sample every few pixels for efficiency
        step = max(1, min(width, height) // 100)

        for y in range(0, height, step):
            for x in range(0, width, step):
                # Get pixel color
                try:
                    r, g, b = img.get(x, y)
                    # Check if pixel is not fully transparent (assuming white/light background)
                    if not (r > 250 and g > 250 and b > 250):
                        left = min(left, x)
                        right = max(right, x)
                        top = min(top, y)
                        bottom = max(bottom, y)
                except:
                    # Some pixels might not be accessible
                    continue

        # Add small margin
        margin = 5
        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(width - 1, right + margin)
        bottom = min(height - 1, bottom + margin)

        return left, top, right, bottom

    @staticmethod
    def create_scaled_icon(source_img: tk.PhotoImage, target_size: int) -> tk.PhotoImage:
        """Create a scaled version of the source image.

        Args:
            source_img: Source PhotoImage
            target_size: Target size (square)

        Returns:
            Scaled PhotoImage
        """
        # Get content bounds
        left, top, right, bottom = AppIcon.find_content_bounds(source_img)
        content_width = right - left
        content_height = bottom - top

        # Calculate scale to fit in target size
        scale = min(target_size / content_width, target_size / content_height) * 0.9  # 90% to leave margin

        # Create new image
        new_img = tk.PhotoImage(width=target_size, height=target_size)

        # Calculate centering offsets
        scaled_width = int(content_width * scale)
        scaled_height = int(content_height * scale)
        x_offset = (target_size - scaled_width) // 2
        y_offset = (target_size - scaled_height) // 2

        # Simple scaling - sample from source
        for y in range(scaled_height):
            for x in range(scaled_width):
                # Map to source coordinates
                src_x = left + int(x / scale)
                src_y = top + int(y / scale)

                try:
                    # Get color from source
                    color = source_img.get(src_x, src_y)
                    # Put in target image
                    new_img.put(f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}",
                              (x_offset + x, y_offset + y))
                except:
                    pass

        return new_img

    @staticmethod
    def load_png_icon() -> Optional[tk.PhotoImage]:
        """Load the PNG microphone icon.

        Returns:
            PhotoImage or None if loading fails
        """
        try:
            # Get the path to the PNG file
            icon_path = Path(__file__).parent.parent / "resources" / "microphone.png"

            if not icon_path.exists():
                print(f"Icon file not found: {icon_path}")
                return None

            # Create a temporary root window to load the image
            temp_root = tk.Tk()
            temp_root.withdraw()

            # Load the PNG
            img = tk.PhotoImage(file=str(icon_path), master=temp_root)

            # Don't destroy temp_root yet, as it owns the image
            # The image will be copied when scaled

            return img

        except Exception as e:
            print(f"Error loading PNG icon: {e}")
            return None

    @staticmethod
    def create_icon(size: int = 128) -> Optional[tk.PhotoImage]:
        """Create icon from PNG file.

        Args:
            size: Target icon size in pixels (default 128 for better quality)

        Returns:
            PhotoImage object or None if creation fails
        """
        try:
            # Get the path to the PNG file
            icon_path = Path(__file__).parent.parent / "resources" / "microphone.png"

            if not icon_path.exists():
                print(f"Icon file not found: {icon_path}")
                return AppIcon.create_fallback_icon(size)

            # Simply load and return the PNG at original size
            # macOS can handle large icons and will scale them as needed
            img = tk.PhotoImage(file=str(icon_path))

            print(f"Loaded icon: {img.width()}x{img.height()} pixels")

            return img

        except Exception as e:
            print(f"Error creating icon from PNG: {e}")
            return AppIcon.create_fallback_icon(size)

    @staticmethod
    def create_fallback_icon(size: int = 64) -> Optional[tk.PhotoImage]:
        """Create a simple fallback icon if PNG loading fails.

        Args:
            size: Icon size in pixels

        Returns:
            PhotoImage with basic microphone shape
        """
        try:
            img = tk.PhotoImage(width=size, height=size)

            cx = size // 2
            cy = size // 2

            # Simple microphone shape
            # Background
            for x in range(size):
                for y in range(size):
                    img.put("#f0f0f0", (x, y))

            # Microphone body
            mic_width = size // 5
            mic_height = size // 2
            mic_top = cy - mic_height // 2

            for x in range(cx - mic_width//2, cx + mic_width//2):
                for y in range(mic_top, mic_top + mic_height):
                    img.put("#404040", (x, y))

            # Microphone head
            head_size = mic_width
            for x in range(cx - head_size//2, cx + head_size//2):
                for y in range(mic_top - head_size//2, mic_top + head_size//2):
                    dx = x - cx
                    dy = y - (mic_top - head_size//2 + head_size//2)
                    if dx*dx + dy*dy <= (head_size//2) ** 2:
                        img.put("#606060", (x, y))

            return img

        except Exception as e:
            print(f"Error creating fallback icon: {e}")
            return None

    @staticmethod
    def create_simple_icon() -> Optional[tk.PhotoImage]:
        """Create a simple icon as fallback.

        Returns:
            PhotoImage with basic microphone shape
        """
        # Use the icon at default size
        return AppIcon.create_icon(64)