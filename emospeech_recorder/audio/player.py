"""Audio playback with hardware-synchronized position updates.

This module implements the playback system with struct-based
shared memory for inter-process communication.
"""

import time
import numpy as np
import sounddevice as sd
from typing import Optional
import multiprocessing as mp
import queue
import traceback

from .audio_buffer import AudioBuffer
from .shared_state import SharedState
from ..utils.config import AudioConfig
from ..utils.audio_utils import calculate_blocksize


class AudioPlayer:
    """Audio player with struct-based synchronized position updates."""

    def __init__(self, config: AudioConfig, shared_state_name: str):
        """Initialize synchronized audio player.

        Args:
            config: Audio configuration
            shared_state_name: Name of shared memory block
        """
        self.config = config

        # Attach to existing shared state
        self.shared_state = SharedState(create=False)
        self.shared_state.attach_to_existing(shared_state_name)

        # Playback state
        self.audio_buffer: Optional[AudioBuffer] = None
        self.audio_data: Optional[np.ndarray] = None
        self.current_position = 0
        self.stream: Optional[sd.OutputStream] = None
        self._stop_requested = False

        # Calculate blocksize from response time setting
        self.blocksize = calculate_blocksize(
            config.sync_response_time_ms,
            config.sample_rate
        )

        self._callback_count = 0


    def start_playback(self, audio_data: np.ndarray, sample_rate: int, audio_buffer: AudioBuffer) -> None:
        """Start synchronized playback.

        Args:
            audio_data: Audio samples to play
            sample_rate: Sample rate in Hz
            audio_buffer: Audio buffer containing the shared memory
        """
        # Stop any current playback
        self.stop_playback()
        time.sleep(0.1)

        # Use provided SHM buffer with normalized data
        self.audio_buffer = audio_buffer
        self.audio_data = audio_buffer.get_array()  # Zero-copy

        # Reset positions
        self.current_position = 0
        self._stop_requested = False
        self._callback_count = 0

        # Update shared state with initial position
        self.shared_state.start_playback(len(audio_data), sample_rate)
        self.shared_state.update_playback_position(0, 0.0)

        # Create output stream with callback
        self.stream = sd.OutputStream(
            samplerate=sample_rate,
            blocksize=self.blocksize,
            device=self.config.output_device,
            channels=1,  # Mono for now
            dtype='float32',  # Always use float32 for sounddevice
            callback=self._audio_callback,
            finished_callback=self._finished_callback
        )
        self.stream.start()

    def stop_playback(self) -> None:
        """Stop playback and clean up."""
        # Set stop flag first
        self._stop_requested = True

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            finally:
                self.stream = None

        self.shared_state.stop_playback()

        # Clean up shared buffer
        if self.audio_buffer:
            self.audio_buffer.close()
            # Don't unlink here - the buffer was created by main process
            self.audio_buffer = None
            self.audio_data = None

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                       time_info, status) -> None:
        """Audio stream callback with hardware timing.

        Args:
            outdata: Output buffer to fill
            frames: Number of frames to provide
            time_info: Hardware timing information
            status: Callback status flags
        """
        if status:
            print(f"Playback callback status: {status}")

        # Check if stop was requested
        if self._stop_requested:
            outdata.fill(0)
            raise sd.CallbackStop()

        # Update shared state with hardware timing
        self.shared_state.update_playback_position(
            self.current_position,
            time_info.outputBufferDacTime
        )


        # Fill output buffer
        if self.audio_data is not None:
            remaining = len(self.audio_data) - self.current_position

            if remaining > 0:
                # Copy audio data
                to_copy = min(frames, remaining)
                outdata[:to_copy, 0] = self.audio_data[
                    self.current_position:self.current_position + to_copy
                ]

                # Fill rest with silence if needed
                if to_copy < frames:
                    outdata[to_copy:] = 0

                # Update position
                self.current_position += to_copy

                # Check if this is the last buffer
                next_position = self.current_position + frames
                if self.current_position < len(self.audio_data) <= next_position:
                    # This is the last buffer - mark as finishing
                    self.shared_state.mark_playback_finishing()

                # Check if we've reached the end
                if self.current_position >= len(self.audio_data):
                    # Signal that playback is completed
                    self.shared_state.mark_playback_completed()
                    self._stop_requested = True
                    # Return stop signal
                    raise sd.CallbackStop()
            else:
                # No more audio, output silence and stop
                outdata.fill(0)
                self.shared_state.stop_playback()
                self._stop_requested = True
                raise sd.CallbackStop()
        else:
            # No audio loaded
            outdata.fill(0)

    def _finished_callback(self) -> None:
        """Called when stream finishes."""
        self.shared_state.stop_playback()
        self.stream = None

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop_playback()
        if self.shared_state:
            self.shared_state.close()


def playback_process(config: AudioConfig,
                           control_queue: mp.Queue,
                           shared_state_name: str) -> None:
    """Process function for audio playback with hardware synchronization.

    Args:
        config: Audio configuration
        control_queue: Queue for control commands
        shared_state_name: Name of shared memory block
    """
    player = None
    attached_buffer: Optional[AudioBuffer] = None

    try:
        # Create player with shared state
        player = AudioPlayer(config, shared_state_name)

        while True:
            try:
                command = control_queue.get(timeout=0.1)

                if isinstance(command, dict):
                    action = command.get('action')

                    if action == 'play':
                        # Get audio buffer metadata
                        buffer_metadata = command.get('buffer_metadata')
                        if buffer_metadata:
                            # Attach to shared audio buffer
                            if attached_buffer:
                                attached_buffer.close()

                            attached_buffer = AudioBuffer.attach_to_existing(
                                buffer_metadata['name'],
                                tuple(buffer_metadata['shape']),
                                np.dtype(buffer_metadata['dtype'])
                            )

                            # Start playback
                            audio_data = attached_buffer.get_array()
                            sample_rate = command.get('sample_rate', config.sample_rate)
                            player.start_playback(audio_data, sample_rate, attached_buffer)

                    elif action == 'stop':
                        player.stop_playback()
                        # Clean up attached buffer when playback stops
                        if attached_buffer:
                            attached_buffer.close()
                            attached_buffer = None

                elif command == 'stop':
                    player.stop_playback()
                    # Clean up attached buffer when playback stops
                    if attached_buffer:
                        attached_buffer.close()
                        attached_buffer = None

                elif command == 'quit':
                    break

            except queue.Empty:
                continue
            except KeyboardInterrupt:
                break

    except Exception as e:
        print(f"Playback process error: {e}")
        traceback.print_exc()

    finally:
        # Cleanup
        if player:
            player.cleanup()
        if attached_buffer:
            attached_buffer.close()