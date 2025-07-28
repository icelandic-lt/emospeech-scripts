"""File management utilities for the recorder."""

from pathlib import Path
from typing import Optional, Tuple, List
import soundfile as sf
import numpy as np

from ..constants import FileConstants, AudioConstants


class RecordingFileManager:
    """Manages recording files and directory structure.

    This class handles all file operations related to audio recordings,
    including file naming, path generation, existence checking, and
    scanning for existing recordings. It supports robust navigation
    through recordings even with gaps in take numbers.

    Attributes:
        recording_dir: Base directory for all recordings

    File Naming Convention:
        Recordings are named as: {label}_{take_number}.wav
        Example: t3_001_1.wav, t3_001_2.wav, etc.
    """

    def __init__(self, recording_dir: Path):
        """Initialize the file manager.

        Args:
            recording_dir: Directory for storing recordings (created if not exists)
        """
        self.recording_dir = Path(recording_dir)
        self.recording_dir.mkdir(exist_ok=True)

    def get_recording_path(self, label: str, take: int) -> Path:
        """Get the path for a recording file.

        Args:
            label: Script label/ID for the utterance
            take: Take number (1-based)

        Returns:
            Path: Full path to the recording file
        """
        # Check if a WAV file already exists (for playback compatibility)
        wav_filename = f"{label}_{take}{FileConstants.LEGACY_AUDIO_FILE_EXTENSION}"
        wav_path = self.recording_dir / wav_filename
        if wav_path.exists():
            return wav_path

        # Otherwise return FLAC path (for new recordings)
        filename = f"{label}_{take}{FileConstants.AUDIO_FILE_EXTENSION}"
        return self.recording_dir / filename

    def recording_exists(self, label: str, take: int) -> bool:
        """Check if a recording exists.

        Args:
            label: Script label/ID for the utterance
            take: Take number to check

        Returns:
            bool: True if the recording file exists
        """
        # Check for FLAC first (new format)
        flac_filename = f"{label}_{take}{FileConstants.AUDIO_FILE_EXTENSION}"
        flac_path = self.recording_dir / flac_filename
        if flac_path.exists():
            return True
        # Check for WAV (legacy format)
        wav_filename = f"{label}_{take}{FileConstants.LEGACY_AUDIO_FILE_EXTENSION}"
        wav_path = self.recording_dir / wav_filename
        return wav_path.exists()

    def find_latest_take(self, label: str) -> int:
        """Find the latest take number for a label.

        This method finds the last consecutive take starting from 1.
        It stops at the first gap in the sequence.

        Args:
            label: Script label/ID for the utterance

        Returns:
            int: Latest consecutive take number (0 if no recordings)

        Note:
            Use get_highest_take() for finding the actual highest take
            number when gaps may exist.
        """
        take = 0
        while self.recording_exists(label, take + 1):
            take += 1
        return take

    def get_highest_take(self, label: str) -> int:
        """Find the highest take number for a label (handles gaps).

        Unlike find_latest_take(), this method finds the actual highest
        take number by scanning all files matching the label pattern,
        even if there are gaps in the numbering.

        Args:
            label: Script label/ID for the utterance

        Returns:
            int: Highest take number found (0 if no recordings)

        Example:
            If files exist: label_1.wav, label_3.wav, label_7.wav
            Returns: 7
        """
        # Check for both FLAC and WAV files
        flac_pattern = f"{label}_*{FileConstants.AUDIO_FILE_EXTENSION}"
        wav_pattern = f"{label}_*{FileConstants.LEGACY_AUDIO_FILE_EXTENSION}"
        files = list(self.recording_dir.glob(flac_pattern)) + list(self.recording_dir.glob(wav_pattern))

        highest = 0
        for file in files:
            # Extract take number from filename
            try:
                # Filename format: label_take.wav
                take_str = file.stem.split('_')[-1]
                take = int(take_str)
                highest = max(highest, take)
            except (ValueError, IndexError):
                # Skip files that don't match expected format
                continue

        return highest

    def scan_all_takes(self, labels: List[str]) -> dict[str, int]:
        """Scan for all existing takes for given labels.

        Efficiently scans the recording directory to find the highest
        take number for each label in the provided list.

        Args:
            labels: List of script labels to scan

        Returns:
            dict: Mapping of label to highest take number
        """
        takes = {}
        for label in labels:
            takes[label] = self.get_highest_take(label)
        return takes

    def load_audio(self, filepath: Path) -> Tuple[np.ndarray, int]:
        """Load audio file and return data with sample rate.

        Loads audio data using soundfile, automatically converting
        stereo to mono if necessary.

        Args:
            filepath: Path to the audio file

        Returns:
            Tuple[np.ndarray, int]: Audio data (normalized -1 to 1) and sample rate

        Raises:
            FileNotFoundError: If the audio file doesn't exist

        Note:
            Audio data is returned normalized between -1 and 1,
            regardless of the original bit depth.
        """
        if not filepath.exists():
            raise FileNotFoundError(f"Audio file not found: {filepath}")

        data, sample_rate = sf.read(str(filepath))

        # Convert to mono if stereo
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        return data, sample_rate

    def save_audio(self, filepath: Path, data: np.ndarray,
                   sample_rate: int, subtype: str) -> None:
        """Save audio data to file.

        Args:
            filepath: Output file path
            data: Audio data array
            sample_rate: Sample rate in Hz
            subtype: Audio subtype (e.g., 'PCM_16', 'PCM_24', or None for FLAC)
        """
        if subtype:
            sf.write(str(filepath), data, sample_rate, subtype=subtype)
        else:
            # For FLAC, let soundfile determine format from extension
            sf.write(str(filepath), data, sample_rate)

    def get_available_takes(self, label: str) -> List[int]:
        """Get list of available take numbers for a label.

        This method only returns consecutive takes starting from 1,
        stopping at the first gap.

        Args:
            label: Script label/ID

        Returns:
            List[int]: List of consecutive take numbers

        Note:
            Use get_existing_takes() to get all takes including
            those with gaps.
        """
        takes = []
        take = 1
        while self.recording_exists(label, take):
            takes.append(take)
            take += 1
        return takes

    def get_existing_takes(self, label: str) -> List[int]:
        """Get list of all existing take numbers for a label, including with gaps.

        Unlike get_available_takes(), this method finds all takes
        by pattern matching, so it handles non-consecutive numbering.

        Args:
            label: Recording label

        Returns:
            List[int]: Sorted list of existing take numbers

        Example:
            If files exist: label_1.wav, label_3.wav, label_7.wav
            Returns: [1, 3, 7]
        """
        # Check for both FLAC and WAV files
        flac_pattern = f"{label}_*{FileConstants.AUDIO_FILE_EXTENSION}"
        wav_pattern = f"{label}_*{FileConstants.LEGACY_AUDIO_FILE_EXTENSION}"
        files = list(self.recording_dir.glob(flac_pattern)) + list(self.recording_dir.glob(wav_pattern))

        existing_takes = []
        for file in files:
            try:
                # Extract take number from filename: label_take.wav
                take_str = file.stem.split('_')[-1]
                take = int(take_str)
                existing_takes.append(take)
            except (ValueError, IndexError):
                # Skip files that don't match expected format
                continue

        return sorted(existing_takes)


class ScriptFileManager:
    """Manages script files in Festival data format.

    This class handles loading and saving script files that contain
    utterances to be recorded. Scripts use the Festival data format:
    (label "utterance text")
    """

    @staticmethod
    def load_script(filepath: Path) -> Tuple[List[str], List[str]]:
        """Load and parse script file in Festival data format.

        Parses files in the format:
        (label1 "utterance text 1")
        (label2 "utterance text 2")

        Args:
            filepath: Path to the script file

        Returns:
            Tuple[List[str], List[str]]: Lists of labels and utterances

        Raises:
            FileNotFoundError: If the script file doesn't exist
        """
        if not filepath.exists():
            raise FileNotFoundError(f"Script file not found: {filepath}")

        with open(filepath) as f:
            lines = f.readlines()

        # Parse Festival data format: (label "utterance")
        labels = []
        utterances = []

        for line in lines:
            # Strip whitespace and parentheses
            line = line.strip('( )\n')
            if not line:
                continue

            # Split on first space followed by quote
            parts = line.split(' "', 1)
            if len(parts) == 2:
                label = parts[0].strip()
                utterance = parts[1].strip('"')
                labels.append(label)
                utterances.append(utterance)

        return labels, utterances

    @staticmethod
    def save_script(filepath: Path, labels: List[str], utterances: List[str]) -> None:
        """Save script in Festival data format.

        Args:
            filepath: Output file path
            labels: List of utterance labels/IDs
            utterances: List of utterance texts

        Raises:
            ValueError: If labels and utterances have different lengths
        """
        if len(labels) != len(utterances):
            raise ValueError("Labels and utterances must have same length")

        with open(filepath, 'w') as f:
            for label, utterance in zip(labels, utterances):
                f.write(f'({label} "{utterance}")\n')


class ConfigFileManager:
    """Manages configuration files.

    This class handles loading and saving configuration files
    for the recorder application. Configuration files are stored
    in the user's home directory.
    """

    @staticmethod
    def get_default_config_path() -> Path:
        """Get the default configuration file path.

        Returns:
            Path: Path to ~/.emospeech_recorder/config.json
        """
        return Path.home() / '.emospeech_recorder' / 'config.json'

    @staticmethod
    def ensure_config_dir() -> None:
        """Ensure configuration directory exists.

        Creates the ~/.emospeech_recorder directory if it doesn't exist.
        """
        config_dir = ConfigFileManager.get_default_config_path().parent
        config_dir.mkdir(parents=True, exist_ok=True)