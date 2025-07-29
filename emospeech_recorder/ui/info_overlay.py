"""Info overlay widget for displaying audio file information."""

import tkinter as tk
from typing import Optional, Tuple
from pathlib import Path
import soundfile as sf

from ..constants import UIConstants


class InfoOverlay:
    """Overlay widget that displays audio file information.

    Shows actual file properties and recording duration.
    Positioned in top-right corner below REC indicator.
    """

    def __init__(self, parent: tk.Widget):
        """Initialize the info overlay.

        Args:
            parent: Parent widget to overlay on
        """
        self.parent = parent
        self.visible = False

        # Create overlay frame
        self.frame = tk.Frame(
            parent,
            bg='black',
            highlightthickness=2,
            highlightbackground='green',
            highlightcolor='green',
            relief='solid',
            borderwidth=1
        )
        self.frame.configure(background='black')

        # Create content labels
        self._create_labels()

    def _create_labels(self) -> None:
        """Create labels for displaying information."""
        # Info section
        self.info_frame = tk.Frame(self.frame, bg='black')
        self.info_frame.pack(pady=20, padx=25)

        # Sample rate
        self.sample_rate_label = tk.Label(
            self.info_frame,
            text="",
            fg='green',
            bg='black',
            font=('Helvetica', 14),
            anchor='w'
        )
        self.sample_rate_label.pack(anchor='w', fill='x', pady=2)

        # Bit depth
        self.bit_depth_label = tk.Label(
            self.info_frame,
            text="",
            fg='green',
            bg='black',
            font=('Helvetica', 14),
            anchor='w'
        )
        self.bit_depth_label.pack(anchor='w', fill='x', pady=2)

        # Format/Channels
        self.format_label = tk.Label(
            self.info_frame,
            text="",
            fg='green',
            bg='black',
            font=('Helvetica', 14),
            anchor='w'
        )
        self.format_label.pack(anchor='w', fill='x', pady=2)

        # Duration
        self.duration_label = tk.Label(
            self.info_frame,
            text="",
            fg='green',
            bg='black',
            font=('Helvetica', 14),
            anchor='w'
        )
        self.duration_label.pack(anchor='w', fill='x', pady=2)

        # File size
        self.size_label = tk.Label(
            self.info_frame,
            text="",
            fg='green',
            bg='black',
            font=('Helvetica', 14),
            anchor='w'
        )
        self.size_label.pack(anchor='w', fill='x', pady=2)

    def _get_file_info(self, file_path: Path) -> Optional[Tuple[int, int, str, int, float]]:
        """Get audio file information.

        Args:
            file_path: Path to audio file

        Returns:
            Tuple of (sample_rate, bit_depth, format, channels, duration) or None
        """
        try:
            info = sf.info(str(file_path))

            # Determine bit depth from subtype
            bit_depth = 16  # default
            if 'PCM_24' in info.subtype or 'FLAC' in info.subtype:
                bit_depth = 24
            elif 'PCM_16' in info.subtype:
                bit_depth = 16

            # Format
            format_name = 'FLAC' if info.format == 'FLAC' else 'WAV'

            return (info.samplerate, bit_depth, format_name, info.channels, info.duration)
        except Exception as e:
            print(f"Error reading file info: {e}")
            return None

    def show(self, file_path: Optional[Path] = None, is_recording: bool = False,
             recording_params: Optional[dict] = None) -> None:
        """Show the overlay with file information.

        Args:
            file_path: Path to audio file
            is_recording: Whether currently recording
            recording_params: Dict with recording parameters (sample_rate, bit_depth, channels)
        """
        if is_recording and recording_params:
            # Show actual recording parameters
            self.sample_rate_label.config(text=f"{recording_params.get('sample_rate', 48000)} Hz")
            self.bit_depth_label.config(text=f"{recording_params.get('bit_depth', 24)} bit")
            channels = recording_params.get('channels', 1)
            channel_text = "Mono" if channels == 1 else "Stereo"
            self.format_label.config(text=f"Recording {channel_text}")
            self.duration_label.config(text="Recording...")
            self.size_label.config(text="")
        elif file_path and file_path.exists():
            # Get file info
            file_info = self._get_file_info(file_path)

            if file_info:
                sample_rate, bit_depth, format_name, channels, duration = file_info

                # Update labels
                self.sample_rate_label.config(text=f"{sample_rate} Hz")
                self.bit_depth_label.config(text=f"{bit_depth} bit")

                channel_text = "Mono" if channels == 1 else "Stereo"
                self.format_label.config(text=f"{format_name} {channel_text}")

                # Duration
                minutes = int(duration // 60)
                seconds = duration % 60
                duration_text = f"{minutes}:{seconds:05.2f}" if minutes > 0 else f"{seconds:.2f}s"
                self.duration_label.config(text=duration_text)

                # File size
                size_bytes = file_path.stat().st_size
                if size_bytes < 1024:
                    size_text = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_text = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_text = f"{size_bytes / (1024 * 1024):.1f} MB"
                self.size_label.config(text=size_text)
            else:
                self.sample_rate_label.config(text="Error reading file")
                self.bit_depth_label.config(text="")
                self.format_label.config(text="")
                self.duration_label.config(text="")
                self.size_label.config(text="")
        else:
            # No recording
            self.sample_rate_label.config(text="No recording")
            self.bit_depth_label.config(text="")
            self.format_label.config(text="")
            self.duration_label.config(text="")
            self.size_label.config(text="")

        # Show the frame with relative positioning
        self.frame.place(relx=0.98, rely=0.12, anchor='ne')
        self.visible = True

        # Force update to prevent white window
        self.frame.update_idletasks()
        self.parent.update_idletasks()

    def hide(self) -> None:
        """Hide the overlay."""
        self.frame.place_forget()
        self.visible = False

    def toggle(self) -> None:
        """Toggle overlay visibility."""
        if self.visible:
            self.hide()
        else:
            # Mark as visible but don't show content yet
            # Content will be set by the caller
            self.visible = True
            # Place the frame to make it visible
            self.frame.place(relx=0.98, rely=0.12, anchor='ne')

    def _position_overlay(self) -> None:
        """Position the overlay in the top-right corner."""
        self.frame.update_idletasks()
        # Position will be set in show() method

    def update_position(self) -> None:
        """Update the overlay position when window is resized."""
        if self.visible:
            # Re-apply the relative positioning
            self.frame.place(relx=0.98, rely=0.12, anchor='ne')