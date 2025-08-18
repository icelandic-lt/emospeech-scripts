"""Ring buffer manager for shared memory audio buffers.

This module provides a thread-safe ring buffer implementation for managing
shared memory buffers across multiple processes. We usually only use one of
these buffers at the same time, but because of synchronization overhead
at cleanup time, e.g. when switching between monitoring, recording, playback etc.
having multiple valid buffers makes smoother transitions possible.
"""

import threading
from typing import Optional
from collections import deque
import time

from .audio_buffer import AudioBuffer


class BufferManager:
    """Manages a ring buffer of shared memory audio buffers.

    This class ensures lifecycle management of shared memory buffers
    by maintaining a fixed-size pool and controlling when buffers are freed.
    """

    def __init__(self, max_buffers: int = 5):
        """Initialize buffer manager.

        Args:
            max_buffers: Maximum number of buffers to keep in the ring
        """
        self.max_buffers = max_buffers
        self.buffers: deque = deque(maxlen=max_buffers)
        self.lock = threading.Lock()
        self._active_buffer: Optional[AudioBuffer] = None
        self._shutdown = False

    def create_buffer(self, audio_data) -> AudioBuffer:
        """Create a new audio buffer and add to ring.

        Args:
            audio_data: Audio data to store in buffer

        Returns:
            Created AudioBuffer instance
        """
        with self.lock:
            # Create new buffer
            buffer = AudioBuffer.create_from_array(audio_data)

            # If ring is full, clean up oldest buffer
            if len(self.buffers) >= self.max_buffers:
                old_buffer = self.buffers[0]  # Will be removed by append
                # Schedule cleanup after a delay to ensure processes are done
                threading.Timer(0.5, self._cleanup_buffer, args=[old_buffer]).start()

            # Add to ring
            self.buffers.append(buffer)
            self._active_buffer = buffer

            return buffer

    @staticmethod
    def _cleanup_buffer(buffer: AudioBuffer) -> None:
        """Clean up a buffer that's no longer needed.

        Args:
            buffer: Buffer to clean up
        """
        try:
            buffer.unlink()
        except Exception:
            pass  # Already unlinked or other error
        try:
            buffer.close()
        except Exception:
            pass

    def get_active_buffer(self) -> Optional[AudioBuffer]:
        """Get the currently active buffer.

        Returns:
            Active AudioBuffer or None
        """
        with self.lock:
            return self._active_buffer

    def cleanup_all(self, wait_time: float = 1.0) -> None:
        """Clean up all buffers after waiting for processes.

        Args:
            wait_time: Time to wait before cleanup (seconds)
        """
        with self.lock:
            self._shutdown = True

        # Wait for child processes to finish with buffers
        time.sleep(wait_time)

        with self.lock:
            # Clean up all buffers
            while self.buffers:
                buffer = self.buffers.popleft()
                self._cleanup_buffer(buffer)

            self._active_buffer = None
