"""Audio playback with hardware-synchronized position updates.

This module implements the playback system with struct-based
shared memory for inter-process communication.
"""

import time
import numpy as np
import sounddevice as sd
from typing import Optional, Any
import multiprocessing as mp
import queue
import traceback

from .audio_buffer import AudioBuffer
from .shared_state import SharedState
from .level_calculator import LevelCalculator
from ..utils.config import AudioConfig
from ..utils.audio_utils import calculate_blocksize
from ..constants import UIConstants


class AudioPlayer:
    """Audio player with synchronized position updates."""

    def __init__(self, config: AudioConfig, shared_state_name: str):
        """Initialize audio player.

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
            config.sync_response_time_ms, config.sample_rate
        )

        # Level calculator for meter updates
        self.level_calculator = LevelCalculator(config.sample_rate)

    def set_output_device(self, index: Optional[int]) -> None:
        """Update output device index used for future streams."""
        self.config.output_device = index

    def start_playback(
        self, audio_data: np.ndarray, sample_rate: int, audio_buffer: AudioBuffer
    ) -> None:
        """Start playback.

        Args:
            audio_data: Audio samples to play
            sample_rate: Sample rate in Hz
            audio_buffer: Audio buffer containing the shared memory
        """
        # Stop any current playback
        self.stop_playback()
        # Give the audio system time to release resources (empirically determined)
        time.sleep(UIConstants.AUDIO_PROCESS_SLEEP)

        # Use provided SHM buffer with normalized data
        self.audio_buffer = audio_buffer
        self.audio_data = audio_buffer.get_array()  # Zero-copy

        # Reset positions
        self.current_position = 0
        self._stop_requested = False

        # Update level calculator sample rate if needed
        self.level_calculator.update_sample_rate(sample_rate)
        self.level_calculator.reset()

        # Update shared state with initial position
        self.shared_state.start_playback(len(audio_data), sample_rate)
        self.shared_state.update_playback_position(0, 0.0)

        # Create output stream with callback
        # Optional routing to a specific physical output channel: we emulate mapping
        # by opening a stream with enough channels and writing only to the target one.
        output_mapping = getattr(self, "_output_channel_mapping", None)
        target_channel_index = 0
        num_stream_channels = 1
        if isinstance(output_mapping, list) and len(output_mapping) == 1:
            try:
                target_channel_index = int(output_mapping[0])
                num_stream_channels = max(1, target_channel_index + 1)
            except Exception:
                target_channel_index = 0
                num_stream_channels = 1

        # Store for callback use
        self._playback_output_channel_index = target_channel_index

        # Open stream with fallback to default device
        try:
            self.stream = sd.OutputStream(
                samplerate=sample_rate,
                blocksize=self.blocksize,
                device=self.config.output_device,
                channels=num_stream_channels,
                dtype="float32",  # Always use float32 for sounddevice
                callback=self._audio_callback,
                finished_callback=self._finished_callback,
            )
        except (sd.PortAudioError, OSError) as e:
            try:
                self.stream = sd.OutputStream(
                    samplerate=sample_rate,
                    blocksize=self.blocksize,
                    device=None,
                    channels=num_stream_channels,
                    dtype="float32",
                    callback=self._audio_callback,
                    finished_callback=self._finished_callback,
                )
            except (sd.PortAudioError, OSError) as e:
                print(f"Error opening OutputStream: {e}")
                self._stop_requested = True
                return
        self.stream.start()

    def stop_playback(self) -> None:
        """Stop playback and clean up."""
        # Set stop flag first
        self._stop_requested = True

        # Store stream reference locally to avoid race conditions
        stream = self.stream
        if stream:
            try:
                stream.stop()
                stream.close()
            except (sd.PortAudioError, RuntimeError) as e:
                # Handle sounddevice specific errors
                print(f"Error stopping audio stream: {e}")
            finally:
                self.stream = None

        self.shared_state.stop_playback()

        # Clean up shared buffer
        if self.audio_buffer:
            self.audio_buffer.close()
            # Don't unlink here - the buffer was created by main process
            self.audio_buffer = None
            self.audio_data = None

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Optional[sd.CallbackFlags],
    ) -> None:
        """Audio stream callback with hardware timing.

        Args:
            outdata: Output buffer to fill
            frames: Number of frames to provide
            time_info: Hardware timing information from sounddevice
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
            self.current_position, time_info.outputBufferDacTime
        )
        # Explicitly mark PLAYING to avoid early IDLE reads
        self.shared_state.set_playback_state(status=2)

        # Fill output buffer
        if self.audio_data is not None:
            remaining = len(self.audio_data) - self.current_position

            if remaining > 0:
                # Copy audio data
                to_copy = min(frames, remaining)
                audio_chunk = self.audio_data[
                    self.current_position : self.current_position + to_copy
                ]
                out_channel_index = getattr(self, "_playback_output_channel_index", 0)
                # Only clear buffer if using multi-channel output
                if outdata.shape[1] > 1:
                    outdata.fill(0)
                # Guard channel index within bounds
                if 0 <= out_channel_index < outdata.shape[1]:
                    outdata[:to_copy, out_channel_index] = audio_chunk

                # Calculate and update level meter
                if to_copy > 0:
                    rms_db, peak_db, peak_hold_db = self.level_calculator.process(
                        audio_chunk.reshape(-1, 1), 1  # Reshape for mono
                    )
                    self.shared_state.update_level_meter(
                        rms_db=rms_db,
                        peak_db=peak_db,
                        peak_hold_db=peak_hold_db,
                        frame_count=self.level_calculator.get_frame_count(),
                    )

                # Fill rest with silence if needed
                if to_copy < frames:
                    outdata[to_copy:] = 0

                # Update position
                self.current_position += to_copy

                # Pre-emptively detect if the next callback will exceed the audio data length.
                # This gives the UI time to prepare for playback end before it actually happens.
                next_position = self.current_position + frames
                if self.current_position < len(self.audio_data) <= next_position:
                    # Signal that we're in the last buffer before completion
                    self.shared_state.mark_playback_finishing()

                # Check if we've actually reached the end
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

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop_playback()
        if self.shared_state:
            self.shared_state.close()


def playback_process(
    config: AudioConfig,
    control_queue: mp.Queue,
    shared_state_name: str,
    shutdown_event: mp.Event,
) -> None:
    """Process function for audio playback with hardware synchronization.

    Args:
        config: Audio configuration
        control_queue: Queue for control commands
        shared_state_name: Name of shared memory block
        shutdown_event: End Playback process ?
    """
    player = None
    attached_buffer: Optional[AudioBuffer] = None

    try:
        # Create player with shared state
        player = AudioPlayer(config, shared_state_name)

        while True:
            try:
                command = control_queue.get(timeout=UIConstants.PROCESS_JOIN_TIMEOUT)

                # Only accept dictionary commands for consistency
                if not isinstance(command, dict):
                    print(f"Warning: Received non-dictionary command: {command}")
                    continue

                action = command.get("action")

                if action == "play":
                    # Get audio buffer metadata
                    buffer_metadata = command.get("buffer_metadata")
                    if buffer_metadata:
                        # Attach to shared audio buffer
                        if attached_buffer:
                            attached_buffer.close()

                        attached_buffer = AudioBuffer.attach_to_existing(
                            buffer_metadata["name"],
                            tuple(buffer_metadata["shape"]),
                            np.dtype(buffer_metadata["dtype"]),
                        )

                        # Start playback
                        audio_data = attached_buffer.get_array()
                        sample_rate = command.get("sample_rate", config.sample_rate)
                        player.start_playback(audio_data, sample_rate, attached_buffer)

                elif action == "stop":
                    player.stop_playback()
                    # Clean up attached buffer when playback stops
                    if attached_buffer:
                        attached_buffer.close()
                        attached_buffer = None

                elif action == "quit":
                    break

                elif action == "set_output_device":
                    value = command.get("index", None)
                    if isinstance(value, int):
                        player.set_output_device(value)
                    elif value is None:
                        player.set_output_device(None)

                elif action == "set_output_channel_mapping":
                    mapping = command.get("mapping", None)
                    try:
                        if isinstance(mapping, list):
                            mapping = [int(x) for x in mapping]
                            player._output_channel_mapping = mapping
                        else:
                            player._output_channel_mapping = None
                    except Exception:
                        player._output_channel_mapping = None

                else:
                    print(f"Warning: Unsupported action: {action}")

            except queue.Empty:
                if shutdown_event.is_set():
                    break
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
