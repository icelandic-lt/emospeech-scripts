"""Audio recording functionality."""

from typing import Optional, Callable, Any
import multiprocessing as mp
import queue
import sounddevice as sd
import numpy as np
import soundfile as sf
from pathlib import Path
import traceback

from ..constants import AudioConstants, FileConstants
from ..utils.config import AudioConfig


class AudioRecorder:
    """Handles audio recording with real-time processing.

    This class manages audio recording using sounddevice, capturing
    audio in real-time and optionally sending chunks to a processing
    queue for visualization. It supports various audio formats and
    devices as configured.

    Attributes:
        config: Audio configuration (device, format, sample rate)
        audio_queue: Queue for sending audio chunks to UI process
        shared_state: Shared dictionary for process communication
        is_recording: Flag indicating recording state
        audio_data: List of recorded audio chunks
        stream: sounddevice InputStream instance
    """

    def __init__(self,
                 config: AudioConfig,
                 audio_queue: mp.Queue,
                 shared_state: dict):
        """Initialize the audio recorder.

        Args:
            config: Audio configuration with device and format settings
            audio_queue: Queue for sending audio data to UI process
            shared_state: Shared state dictionary with 'recording' and
                'audio_queue_active' flags
        """
        self.config = config
        self.audio_queue = audio_queue
        self.shared_state = shared_state

        # Recording state
        self.is_recording = False
        self.audio_data = []

        # Configure sounddevice
        self._configure_audio_device()

    def _configure_audio_device(self) -> None:
        """Configure audio device settings.

        Sets sounddevice defaults for input device, sample rate,
        channels, and data type based on configuration.
        """
        if self.config.input_device is not None:
            sd.default.device[0] = self.config.input_device

        sd.default.samplerate = self.config.sample_rate
        sd.default.channels = self.config.channels
        sd.default.dtype = self.config.dtype

    def start_recording(self) -> None:
        """Start audio recording.

        Initializes recording state and starts a sounddevice input
        stream with a callback for processing audio chunks.
        """
        self.is_recording = True
        self.audio_data = []
        self.shared_state['recording'] = True

        # Start recording stream
        self.stream = sd.InputStream(
            callback=self._audio_callback,
            blocksize=AudioConstants.AUDIO_CHUNK_SIZE,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            device=self.config.input_device
        )
        self.stream.start()

        # Debug: Print actual stream settings
        if self.shared_state.get('debug', False):
            print(f"Recording stream started with:")
            print(f"  Requested sample rate: {self.config.sample_rate} Hz")
            print(f"  Actual sample rate: {self.stream.samplerate} Hz")
            print(f"  Device: {self.stream.device}")
            print(f"  Channels: {self.stream.channels}")
            print(f"  dtype: {self.stream.dtype}")

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return audio data.

        Stops the audio stream and concatenates all recorded chunks
        into a single array.

        Returns:
            np.ndarray: Complete recorded audio data
        """
        self.is_recording = False
        self.shared_state['recording'] = False

        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()

        # Concatenate all audio chunks
        if self.audio_data:
            return np.concatenate(self.audio_data)
        return np.array([])

    def _audio_callback(self, indata: np.ndarray, frames: int,
                       time_info: Any, status: sd.CallbackFlags) -> None:
        """Audio stream callback for recording.

        Called by sounddevice for each audio chunk. Stores data
        and optionally sends to processing queue.

        Args:
            indata: Audio input data
            frames: Number of frames
            time_info: Timing information
            status: Callback status flags
        """
        if status and self.shared_state.get('debug', False):
            print(f"Audio callback status: {status}")

        if self.is_recording:
            # Store audio data
            self.audio_data.append(indata.copy())

            # Debug: Print first callback
            if len(self.audio_data) == 1 and self.shared_state.get('debug', False):
                print(f"First audio callback: shape={indata.shape}, dtype={indata.dtype}, max={np.max(np.abs(indata))}")

            # Send to processing queue if active
            queue_active = self.shared_state.get('audio_queue_active', False)
            if len(self.audio_data) == 1 and self.shared_state.get('debug', False):
                print(f"Audio queue active: {queue_active}")

            if queue_active:
                try:
                    self.audio_queue.put_nowait(indata.copy())
                    if len(self.audio_data) <= 3 and self.shared_state.get('debug', False):  # Print first few
                        print(f"Put audio chunk {len(self.audio_data)} in queue")
                except queue.Full:
                    if self.shared_state.get('debug', False):
                        print("Warning: Audio queue full!")
                except Exception as e:
                    if self.shared_state.get('debug', False):
                        print(f"Error putting audio in queue: {e}")

    def save_recording(self, audio_data: np.ndarray, filepath: Path) -> None:
        """Save audio data to file.

        Args:
            audio_data: Audio samples to save
            filepath: Output file path

        Note:
            Uses soundfile to write with appropriate subtype
            (PCM_16 or PCM_24) based on configuration.
        """
        if filepath.suffix.lower() == '.flac':
            # For FLAC, explicitly set subtype based on bit depth
            if self.config.bit_depth == 24:
                sf.write(
                    str(filepath),
                    audio_data,
                    self.config.sample_rate,
                    subtype='PCM_24'
                )
            else:
                sf.write(
                    str(filepath),
                    audio_data,
                    self.config.sample_rate,
                    subtype='PCM_16'
                )
        elif self.config.subtype:
            # For WAV files, use configured subtype
            sf.write(
                str(filepath),
                audio_data,
                self.config.sample_rate,
                subtype=self.config.subtype
            )
        else:
            # Default behavior
            sf.write(
                str(filepath),
                audio_data,
                self.config.sample_rate
            )


def record_process(config: AudioConfig,
                  audio_queue: mp.Queue,
                  shared_state: dict,
                  control_queue: mp.Queue) -> None:
    """Recording process function for multiprocessing.

    This function runs in a separate process to handle audio recording.
    It listens for commands and manages the recording lifecycle.

    Commands:
        - 'start': Begin recording
        - 'stop': Stop recording and save to file
        - 'quit': Exit the process

    Args:
        config: Audio configuration
        audio_queue: Queue for sending audio data to UI process
        shared_state: Shared state with 'save_path' and flags
        control_queue: Queue for receiving control commands

    Note:
        The save path is retrieved from shared_state['save_path']
        when stopping a recording.
    """
    recorder = AudioRecorder(config, audio_queue, shared_state)

    try:
        while True:
            try:
                command = control_queue.get(timeout=0.1)

                if command == 'start':
                    recorder.start_recording()
                    if shared_state.get('debug', False):
                        print("Recording started")

                elif command == 'stop':
                    audio_data = recorder.stop_recording()

                    # Get save path from shared state
                    save_path = shared_state.get('save_path')
                    if save_path and len(audio_data) > 0:
                        recorder.save_recording(audio_data, Path(save_path))
                        if shared_state.get('debug', False):
                            print(f"Recording saved to {save_path}")

                    # Clear save path
                    shared_state['save_path'] = None

                elif command == 'quit':
                    break

            except queue.Empty:
                continue

    except Exception as e:
        if shared_state.get('debug', False):
            print(f"Recording process error: {e}")
            traceback.print_exc()

    finally:
        # Cleanup
        if recorder.is_recording:
            recorder.stop_recording()