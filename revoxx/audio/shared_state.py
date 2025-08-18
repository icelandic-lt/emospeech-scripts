"""Struct-based shared state for audio synchronization.

This module provides a performant shared state implementation using
struct and shared memory for inter-process communication.
"""

import struct
import time
from multiprocessing import shared_memory
from typing import Optional, Tuple, NamedTuple

from revoxx.constants import AudioConstants


# Status constants
SHARED_STATUS_INVALID = 0  # Uninitialized state

# Playback status
PLAYBACK_STATUS_IDLE = 1
PLAYBACK_STATUS_PLAYING = 2
PLAYBACK_STATUS_FINISHING = 3
PLAYBACK_STATUS_COMPLETED = 4

# Recording status
RECORDING_STATUS_STOPPED = 1
RECORDING_STATUS_ACTIVE = 2

# Audio settings status
SETTINGS_STATUS_VALID = 1

_PLAYBACK_FORMAT = "BxxxdQQdi"  # B=status (first), xxx=padding, then rest


class PlaybackStateFormat(NamedTuple):
    """Format definition for playback state structure."""

    # Format string for struct.pack/unpack
    format: str = _PLAYBACK_FORMAT
    # Field names
    fields: Tuple[str, ...] = (
        "status",  # B - unsigned char (1 byte + 3 padding)
        "hardware_timestamp",  # d - double (8 bytes)
        "current_sample_position",  # Q - unsigned long long (8 bytes)
        "total_samples",  # Q - unsigned long long (8 bytes)
        "update_timestamp",  # d - double (8 bytes)
        "sample_rate",  # i - int (4 bytes)
    )
    # Total size in bytes
    size: int = struct.calcsize(_PLAYBACK_FORMAT)


_RECORDING_FORMAT = "BxxxdQdi"  # B=status (first), xxx=padding, then rest


class RecordingStateFormat(NamedTuple):
    """Format definition for recording state structure."""

    format: str = _RECORDING_FORMAT
    fields: Tuple[str, ...] = (
        "status",  # B - unsigned char (1 byte + 3 padding)
        "hardware_timestamp",  # d - double (8 bytes)
        "current_sample_position",  # Q - unsigned long long (8 bytes)
        "update_timestamp",  # d - double (8 bytes)
        "sample_rate",  # i - int (4 bytes)
    )
    size: int = struct.calcsize(_RECORDING_FORMAT)


# Audio settings format - shared between recording and playback
_AUDIO_SETTINGS_FORMAT = "BxxxiiBBHI"  # B=status (first), xxx=padding, then rest


class AudioSettingsFormat(NamedTuple):
    """Format definition for audio settings structure."""

    format: str = _AUDIO_SETTINGS_FORMAT
    fields: Tuple[str, ...] = (
        "status",  # B - unsigned char (1 byte + 3 padding)
        "sample_rate",  # i - int (4 bytes)
        "bit_depth",  # i - int (4 bytes)
        "channels",  # B - unsigned char (1 byte)
        "format_type",  # B - unsigned char (1 byte) - 0=WAV, 1=FLAC
        "reserved",  # H - unsigned short (2 bytes) - for future use
        "update_counter",  # I - unsigned int (4 bytes) - incremented on each update
    )
    size: int = struct.calcsize(_AUDIO_SETTINGS_FORMAT)


# Level meter format - for real-time audio level monitoring
_LEVEL_METER_FORMAT = "BxxxffffQ"  # B=status (first), xxx=padding, then rest


class LevelMeterFormat(NamedTuple):
    """Format definition for level meter state structure."""

    format: str = _LEVEL_METER_FORMAT
    fields: Tuple[str, ...] = (
        "status",  # B - unsigned char (1 byte + 3 padding)
        "rms_db",  # f - float (4 bytes) - RMS level in dB
        "peak_db",  # f - float (4 bytes) - Peak level in dB
        "peak_hold_db",  # f - float (4 bytes) - Peak hold level in dB
        "update_time",  # f - float (4 bytes) - Update timestamp
        "frame_count",  # Q - unsigned long long (8 bytes) - Frame counter
    )
    size: int = struct.calcsize(_LEVEL_METER_FORMAT)


class SharedState:
    """Shared state using struct and shared memory.

    This class provides zero-copy access to shared audio state between
    processes using fixed-size struct formats.
    """

    def __init__(self, create: bool = True):
        """Initialize struct-based shared state.

        Args:
            create: If True, create new shared memory. If False, attach to existing.
        """
        self.playback_format = PlaybackStateFormat()
        self.recording_format = RecordingStateFormat()
        self.settings_format = AudioSettingsFormat()
        self.level_meter_format = LevelMeterFormat()

        # Calculate total size needed
        self.total_size = (
            self.playback_format.size
            + self.recording_format.size
            + self.settings_format.size
            + self.level_meter_format.size
        )

        # Offsets for each structure
        self.playback_offset = 0
        self.recording_offset = self.playback_format.size
        self.settings_offset = self.recording_offset + self.recording_format.size
        self.level_meter_offset = self.settings_offset + self.settings_format.size

        if create:
            self.shm = shared_memory.SharedMemory(create=True, size=self.total_size)
            # Initialize with zeros to catch initialization bugs
            playback_defaults = struct.pack(
                self.playback_format.format,
                SHARED_STATUS_INVALID,  # status
                0.0,
                0,
                0,
                0.0,
                0,
            )  # rest zeros
            recording_defaults = struct.pack(
                self.recording_format.format,
                SHARED_STATUS_INVALID,  # status
                0.0,
                0,
                0.0,
                0,
            )  # rest zeros
            # Audio settings - all zeros to force correct initialization
            settings_defaults = struct.pack(
                self.settings_format.format,
                SHARED_STATUS_INVALID,  # status
                0,  # sample_rate
                0,  # bit_depth
                0,  # channels
                0,  # format_type
                0,  # reserved
                0,
            )  # update_counter
            # Level meter defaults
            level_meter_defaults = struct.pack(
                self.level_meter_format.format,
                SHARED_STATUS_INVALID,  # status
                AudioConstants.MIN_DB_LEVEL,  # rms_db
                AudioConstants.MIN_DB_LEVEL,  # peak_db
                AudioConstants.MIN_DB_LEVEL,  # peak_hold_db
                0.0,  # update_time
                0,
            )  # frame_count
            # Write packed data to buffer
            self.shm.buf[
                self.playback_offset : self.playback_offset + self.playback_format.size
            ] = playback_defaults
            self.shm.buf[
                self.recording_offset : self.recording_offset
                + self.recording_format.size
            ] = recording_defaults
            self.shm.buf[
                self.settings_offset : self.settings_offset + self.settings_format.size
            ] = settings_defaults
            self.shm.buf[
                self.level_meter_offset : self.level_meter_offset
                + self.level_meter_format.size
            ] = level_meter_defaults
        else:
            # Will attach later with attach_to_existing()
            self.shm = None

    def attach_to_existing(self, name: str) -> None:
        """Attach to existing shared memory.

        Args:
            name: Name of existing shared memory block
        """
        if self.shm:
            self.shm.close()
        self.shm = shared_memory.SharedMemory(name=name)

    def close(self) -> None:
        """Close shared memory connection."""
        if self.shm:
            self.shm.close()

    def unlink(self) -> None:
        """Unlink (delete) shared memory."""
        if self.shm:
            self.shm.unlink()

    @property
    def name(self) -> Optional[str]:
        """Get shared memory name for passing to other processes."""
        return self.shm.name if self.shm else None

    # Playback state methods
    def set_playback_state(self, **kwargs) -> None:
        """Set playback state fields.

        Args:
            **kwargs: Keyword arguments for playback state fields:
                - status: Playback status
                - hardware_timestamp: Hardware DAC timestamp
                - current_sample_position: Current playback position
                - total_samples: Total number of samples
                - update_timestamp: System time of update
                - sample_rate: Sample rate in Hz
        """
        # Get current values
        current = self.get_playback_state()

        # Update with new values
        values = []
        for field in self.playback_format.fields:
            if field in kwargs:
                values.append(kwargs[field])
            else:
                values.append(current[field])

        # Pack and write
        data = struct.pack(self.playback_format.format, *values)
        self.shm.buf[
            self.playback_offset : self.playback_offset + self.playback_format.size
        ] = data

    def get_playback_state(self) -> dict:
        """Get current playback state.

        Returns:
            Dictionary with all playback state fields
        """
        data = bytes(
            self.shm.buf[
                self.playback_offset : self.playback_offset + self.playback_format.size
            ]
        )
        values = struct.unpack(self.playback_format.format, data)
        return dict(zip(self.playback_format.fields, values))

    def update_playback_position(
        self, sample_position: int, hardware_timestamp: float
    ) -> None:
        """Update playback position with hardware timing.

        Args:
            sample_position: Current sample position
            hardware_timestamp: Hardware DAC timestamp
        """
        self.set_playback_state(
            current_sample_position=sample_position,
            hardware_timestamp=hardware_timestamp,
            update_timestamp=time.time(),
        )

    # Recording state methods
    def set_recording_state(self, **kwargs) -> None:
        """Set recording state fields.

        Args:
            **kwargs: Keyword arguments for recording state fields:
                - status: Recording status
                - hardware_timestamp: Hardware ADC timestamp
                - current_sample_position: Current recording position
                - update_timestamp: System time of update
                - sample_rate: Sample rate in Hz
        """
        # Get current values
        current = self.get_recording_state()

        # Update with new values
        values = []
        for field in self.recording_format.fields:
            if field in kwargs:
                values.append(kwargs[field])
            else:
                values.append(current[field])

        # Pack and write
        data = struct.pack(self.recording_format.format, *values)
        self.shm.buf[
            self.recording_offset : self.recording_offset + self.recording_format.size
        ] = data

    def get_recording_state(self) -> dict:
        """Get current recording state.

        Returns:
            Dictionary with all recording state fields
        """
        data = bytes(
            self.shm.buf[
                self.recording_offset : self.recording_offset
                + self.recording_format.size
            ]
        )
        values = struct.unpack(self.recording_format.format, data)
        return dict(zip(self.recording_format.fields, values))

    def update_recording_position(
        self, sample_position: int, hardware_timestamp: float
    ) -> None:
        """Update recording position with hardware timing.

        Args:
            sample_position: Current sample position
            hardware_timestamp: Hardware ADC timestamp
        """
        self.set_recording_state(
            current_sample_position=sample_position,
            hardware_timestamp=hardware_timestamp,
            update_timestamp=time.time(),
        )

    # Convenience methods
    def start_playback(self, total_samples: int, sample_rate: int) -> None:
        """Start playback.

        Args:
            total_samples: Total number of samples to play
            sample_rate: Sample rate in Hz
        """
        self.set_playback_state(
            status=PLAYBACK_STATUS_PLAYING,
            total_samples=total_samples,
            sample_rate=sample_rate,
            current_sample_position=0,
        )

    def stop_playback(self) -> None:
        """Stop playback."""
        self.set_playback_state(status=PLAYBACK_STATUS_IDLE)

    def mark_playback_finishing(self) -> None:
        """Mark playback as finishing (last buffer being played)."""
        self.set_playback_state(status=PLAYBACK_STATUS_FINISHING)

    def mark_playback_completed(self) -> None:
        """Mark playback as completed."""
        self.set_playback_state(status=PLAYBACK_STATUS_COMPLETED)

    def start_recording(self, sample_rate: int) -> None:
        """Start recording.

        Args:
            sample_rate: Sample rate in Hz
        """
        self.set_recording_state(
            status=RECORDING_STATUS_ACTIVE,
            sample_rate=sample_rate,
            current_sample_position=0,
        )

    def stop_recording(self) -> None:
        """Stop recording."""
        self.set_recording_state(status=RECORDING_STATUS_STOPPED)

    # Audio settings methods
    def set_audio_settings(self, **kwargs) -> None:
        """Set audio settings.

        Args:
            **kwargs: Keyword arguments for audio settings:
                - sample_rate: Sample rate in Hz
                - bit_depth: Bit depth (16 or 24)
                - channels: Number of channels
                - format_type: Format type (0=WAV, 1=FLAC)
        """
        # Get current values
        current = self.get_audio_settings()

        # Increment update counter
        update_counter = current.get("update_counter", 0) + 1

        # Update with new values
        values = []
        for field in self.settings_format.fields:
            if field == "update_counter":
                values.append(update_counter)
            elif field in kwargs:
                values.append(kwargs[field])
            else:
                values.append(current[field])

        # Pack and write
        data = struct.pack(self.settings_format.format, *values)
        self.shm.buf[
            self.settings_offset : self.settings_offset + self.settings_format.size
        ] = data

    def get_audio_settings(self) -> dict:
        """Get current audio settings.

        Returns:
            Dictionary with all audio settings fields
        """
        data = bytes(
            self.shm.buf[
                self.settings_offset : self.settings_offset + self.settings_format.size
            ]
        )
        values = struct.unpack(self.settings_format.format, data)
        return dict(zip(self.settings_format.fields, values))

    def update_audio_settings(
        self, sample_rate: int, bit_depth: int, channels: int = 1, format_type: int = 0
    ) -> None:
        """Update audio settings.

        Args:
            sample_rate: Sample rate in Hz
            bit_depth: Bit depth (16 or 24)
            channels: Number of channels
            format_type: Format type (0=WAV, 1=FLAC)
        """
        self.set_audio_settings(
            status=SETTINGS_STATUS_VALID,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            format_type=format_type,
        )

    # Level meter methods
    def set_level_meter_state(self, **kwargs) -> None:
        """Set level meter state fields.

        Args:
            **kwargs: Keyword arguments for level meter state fields:
                - status: Level meter status
                - rms_db: RMS level in dB
                - peak_db: Peak level in dB
                - peak_hold_db: Peak hold level in dB
                - update_time: Update timestamp
                - frame_count: Frame counter
        """
        # Get current values
        current = self.get_level_meter_state()

        # Update with new values
        values = []
        for field in self.level_meter_format.fields:
            if field in kwargs:
                values.append(kwargs[field])
            else:
                values.append(current[field])

        # Pack and write
        data = struct.pack(self.level_meter_format.format, *values)
        self.shm.buf[
            self.level_meter_offset : self.level_meter_offset
            + self.level_meter_format.size
        ] = data

    def get_level_meter_state(self) -> dict:
        """Get current level meter state.

        Returns:
            Dictionary with all level meter state fields
        """
        data = bytes(
            self.shm.buf[
                self.level_meter_offset : self.level_meter_offset
                + self.level_meter_format.size
            ]
        )
        values = struct.unpack(self.level_meter_format.format, data)
        return dict(zip(self.level_meter_format.fields, values))

    def update_level_meter(
        self, rms_db: float, peak_db: float, peak_hold_db: float, frame_count: int
    ) -> None:
        """Update level meter values.

        Args:
            rms_db: RMS level in dB
            peak_db: Peak level in dB
            peak_hold_db: Peak hold level in dB
            frame_count: Current frame count
        """
        self.set_level_meter_state(
            status=SETTINGS_STATUS_VALID,  # Reuse settings status for simplicity
            rms_db=rms_db,
            peak_db=peak_db,
            peak_hold_db=peak_hold_db,
            update_time=time.time(),
            frame_count=frame_count,
        )

    def reset_level_meter(self) -> None:
        """Reset level meter values to minimum and bump frame counter.

        Keeps status valid so UI accepts update. Increments frame_count to
        ensure UI detects a change regardless of its local cache.
        """
        current = self.get_level_meter_state()
        next_frame = int(current.get("frame_count", 0)) + 1
        self.set_level_meter_state(
            status=SETTINGS_STATUS_VALID,
            rms_db=AudioConstants.MIN_DB_LEVEL,
            peak_db=AudioConstants.MIN_DB_LEVEL,
            peak_hold_db=AudioConstants.MIN_DB_LEVEL,
            update_time=time.time(),
            frame_count=next_frame,
        )
