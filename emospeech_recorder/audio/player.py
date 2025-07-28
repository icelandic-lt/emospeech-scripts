"""Audio playback functionality."""

from typing import Optional, Callable
import multiprocessing as mp
import queue
import time
import sounddevice as sd
import numpy as np
from pathlib import Path

from ..utils.config import AudioConfig
from ..utils.file_manager import RecordingFileManager


class AudioPlayer:
    """Handles audio playback with interruption support.

    This class provides low-level audio playback functionality using
    sounddevice. It supports interruption via multiprocessing signals,
    allowing playback to be stopped from other processes.

    Attributes:
        config: Audio configuration with device settings
        is_playing: Flag indicating if audio is currently playing
    """

    def __init__(self, config: AudioConfig):
        """Initialize the audio player.

        Args:
            config: Audio configuration containing output device settings
        """
        self.config = config
        self.is_playing = False
        self._configure_audio_device()

    def _configure_audio_device(self) -> None:
        """Configure audio device settings.

        Sets the default output device for sounddevice based on
        configuration. Device can be specified by index or name.
        """
        if self.config.output_device is not None:
            sd.default.device[1] = self.config.output_device

    def play(self, audio_data: np.ndarray, sample_rate: int,
             stop_signal: Optional[mp.Value] = None) -> None:
        """Play audio data with optional interruption.

        Plays audio asynchronously and monitors for stop signals.
        The method blocks until playback completes or is interrupted.

        Args:
            audio_data: Audio samples to play (mono or stereo)
            sample_rate: Sample rate in Hz
            stop_signal: Optional shared value for interruption (1 = stop)

        Note:
            Uses a polling loop to check for interruption every 50ms
        """
        self.is_playing = True

        try:
            # Start playback
            sd.play(audio_data, sample_rate)

            # Wait for playback to finish, checking for stop signal
            while sd.get_stream() and sd.get_stream().active:
                if stop_signal and stop_signal.value:
                    sd.stop()
                    print("Playback interrupted")
                    break
                time.sleep(0.05)  # Check every 50ms

        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            self.is_playing = False

    def stop(self) -> None:
        """Stop current playback.

        Immediately stops any audio currently playing through sounddevice.
        """
        sd.stop()
        self.is_playing = False


def playback_process(config: AudioConfig,
                    recording_dir: Path,
                    control_queue: mp.Queue,
                    shared_state: dict,
                    stop_signal: mp.Value) -> None:
    """Playback process function for multiprocessing.

    This function runs in a separate process to handle audio playback
    commands. It listens for commands on a queue and manages playback
    state in shared memory.

    Commands:
        - {'action': 'play', 'label': str, 'take': int}: Play a recording
        - 'stop': Stop current playback
        - 'quit': Exit the process

    Args:
        config: Audio configuration
        recording_dir: Directory containing recordings
        control_queue: Queue for receiving control commands
        shared_state: Shared state dictionary with 'playing' and 'current_file'
        stop_signal: Signal for interrupting playback (0 = play, 1 = stop)
    """
    player = AudioPlayer(config)
    file_manager = RecordingFileManager(recording_dir)

    print(f"Playback process started in dir: {recording_dir}")

    try:
        while True:
            try:
                command = control_queue.get(timeout=0.1)

                if isinstance(command, dict) and command.get('action') == 'play':
                    # Extract playback parameters
                    label = command.get('label')
                    take = command.get('take', 1)

                    if label:
                        # Load and play audio file
                        filepath = file_manager.get_recording_path(label, take)

                        if filepath.exists():
                            # Reset stop signal before playing
                            stop_signal.value = 0

                            # Update shared state
                            shared_state['playing'] = True
                            shared_state['current_file'] = str(filepath)

                            # Load audio
                            audio_data, sample_rate = file_manager.load_audio(filepath)

                            print(f"Playing file: {filepath}")

                            # Play with interruption support
                            player.play(audio_data, sample_rate, stop_signal)

                            # Update state when done
                            shared_state['playing'] = False
                            shared_state['current_file'] = None
                            print("Playback completed")
                        else:
                            print(f"Recording not found: {filepath}")

                elif command == 'stop':
                    player.stop()
                    stop_signal.value = 1

                elif command == 'quit':
                    break

            except queue.Empty:
                continue

    except Exception as e:
        print(f"Playback process error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        player.stop()
        shared_state['playing'] = False


class PlaybackController:
    """High-level controller for playback operations.

    This class provides a convenient interface for controlling audio
    playback from the main process. It manages communication with the
    playback process via queues and shared state.

    Attributes:
        config: Audio configuration
        recording_dir: Directory containing recordings
        playback_queue: Queue for sending commands
        shared_state: Shared state for status monitoring
        stop_signal: Signal for interrupting playback
        file_manager: Manager for recording file operations
    """

    def __init__(self,
                 config: AudioConfig,
                 recording_dir: Path,
                 playback_queue: mp.Queue,
                 shared_state: dict,
                 stop_signal: mp.Value):
        """Initialize the playback controller.

        Args:
            config: Audio configuration
            recording_dir: Directory containing recordings
            playback_queue: Queue for sending commands to playback process
            shared_state: Shared state dictionary for status monitoring
            stop_signal: Signal for interrupting playback
        """
        self.config = config
        self.recording_dir = recording_dir
        self.playback_queue = playback_queue
        self.shared_state = shared_state
        self.stop_signal = stop_signal
        self.file_manager = RecordingFileManager(recording_dir)

    def play_recording(self, label: str, take: int) -> bool:
        """Play a specific recording.

        Stops any current playback and starts playing the specified
        recording. Checks file existence before sending play command.

        Args:
            label: Recording label/ID
            take: Take number (1-based)

        Returns:
            bool: True if playback started, False if file not found
        """
        # Stop any current playback
        self.stop_playback()

        # Check if file exists
        if not self.file_manager.recording_exists(label, take):
            return False

        # Reset stop signal
        self.stop_signal.value = 0

        # Send play command
        self.playback_queue.put({
            'action': 'play',
            'label': label,
            'take': take
        })

        return True

    def stop_playback(self) -> None:
        """Stop current playback.

        Sets the stop signal and sends stop command to the playback
        process. This will interrupt any audio currently playing.
        """
        self.stop_signal.value = 1
        self.playback_queue.put('stop')

    def is_playing(self) -> bool:
        """Check if audio is currently playing.

        Returns:
            bool: True if audio is playing, False otherwise
        """
        return self.shared_state.get('playing', False)