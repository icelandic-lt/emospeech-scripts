"""Shared memory audio buffer for synchronized playback and recording.

This module provides a shared memory implementation for audio data that can be
accessed by multiple processes.
"""

import numpy as np
from multiprocessing import shared_memory
from typing import Optional, Tuple


class AudioBuffer:
    """Manages shared memory for audio data across processes.

    This class handles allocation, access, and cleanup of shared memory
    used for audio data, allowing multiple processes to access the same
    audio without copying.
    """

    def __init__(self, name: Optional[str] = None):
        """Initialize shared audio buffer.

        Args:
            name: Optional name for existing shared memory block
        """
        self.shm: Optional[shared_memory.SharedMemory] = None
        self.shape: Optional[Tuple[int, ...]] = None
        self.dtype: Optional[np.dtype] = None
        self.name: Optional[str] = name

    @classmethod
    def create_from_array(cls, audio_data: np.ndarray) -> "AudioBuffer":
        """Create a shared buffer from numpy array.

        Args:
            audio_data: Audio data to share

        Returns:
            AudioBuffer instance with data in shared memory
        """
        buffer = cls()

        # Store metadata
        buffer.shape = audio_data.shape
        buffer.dtype = audio_data.dtype

        # Create shared memory
        buffer.shm = shared_memory.SharedMemory(create=True, size=audio_data.nbytes)
        buffer.name = buffer.shm.name

        # Copy data to shared memory
        shared_array = np.ndarray(
            buffer.shape, dtype=buffer.dtype, buffer=buffer.shm.buf
        )
        shared_array[:] = audio_data[:]

        return buffer

    @classmethod
    def attach_to_existing(
        cls, name: str, shape: Tuple[int, ...], dtype: np.dtype
    ) -> "AudioBuffer":
        """Attach to existing shared memory buffer.

        Args:
            name: Name of existing shared memory
            shape: Shape of the array
            dtype: Data type of the array

        Returns:
            AudioBuffer connected to existing memory
        """
        buffer = cls(name=name)
        buffer.shape = shape
        buffer.dtype = dtype

        # Attach to existing shared memory
        buffer.shm = shared_memory.SharedMemory(name=name)

        return buffer

    def get_array(self) -> np.ndarray:
        """Get numpy array view of shared data.

        Returns:
            Numpy array backed by shared memory
        """
        if self.shm is None:
            raise RuntimeError("Shared memory not initialized")

        return np.ndarray(self.shape, dtype=self.dtype, buffer=self.shm.buf)

    def close(self) -> None:
        """Close the shared memory connection."""
        if self.shm is not None:
            self.shm.close()

    def unlink(self) -> None:
        """Unlink (delete) the shared memory block.

        Should only be called by the process that created it.
        """
        if self.shm is not None:
            try:
                self.shm.unlink()
            except FileNotFoundError:
                # Already unlinked
                pass

    def get_metadata(self) -> dict:
        """Get metadata for recreating buffer in another process.

        Returns:
            Dictionary with name, shape, and dtype info
        """
        return {
            "name": self.name,
            "shape": self.shape,
            "dtype": str(self.dtype) if self.dtype else None,
        }
