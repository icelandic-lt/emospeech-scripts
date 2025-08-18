"""Tests for file management utilities."""

import unittest
import tempfile
import shutil
from pathlib import Path
import numpy as np
import soundfile as sf

from emospeech_recorder.utils.file_manager import RecordingFileManager, ScriptFileManager


class TestRecordingFileManager(unittest.TestCase):
    """Test RecordingFileManager functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = Path(self.temp_dir) / "recordings"
        self.manager = RecordingFileManager(self.recording_dir)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_recording_path(self):
        """Test recording path generation."""
        # Test for new recording
        path = self.manager.get_recording_path("utt_001", 1)
        expected = self.recording_dir / "utt_001" / "take_001.flac"
        self.assertEqual(path, expected)

        # Test for multiple takes
        path = self.manager.get_recording_path("utt_001", 123)
        expected = self.recording_dir / "utt_001" / "take_123.flac"
        self.assertEqual(path, expected)

    def test_recording_exists(self):
        """Test checking if recording exists."""
        # Initially no recording
        self.assertFalse(self.manager.recording_exists("utt_001", 1))

        # Create a recording
        utterance_dir = self.recording_dir / "utt_001"
        utterance_dir.mkdir(parents=True)
        test_file = utterance_dir / "take_001.flac"
        test_file.touch()

        # Now it should exist
        self.assertTrue(self.manager.recording_exists("utt_001", 1))
        self.assertFalse(self.manager.recording_exists("utt_001", 2))

    def test_find_latest_take(self):
        """Test finding latest consecutive take."""
        # No recordings
        self.assertEqual(self.manager.find_latest_take("utt_001"), 0)

        # Create consecutive takes
        utterance_dir = self.recording_dir / "utt_001"
        utterance_dir.mkdir(parents=True)
        for i in range(1, 4):
            (utterance_dir / f"take_{i:03d}.flac").touch()

        self.assertEqual(self.manager.find_latest_take("utt_001"), 3)

    def test_get_highest_take(self):
        """Test finding highest take with gaps."""
        # Create takes with gaps
        utterance_dir = self.recording_dir / "utt_001"
        utterance_dir.mkdir(parents=True)
        (utterance_dir / "take_001.flac").touch()
        (utterance_dir / "take_003.flac").touch()
        (utterance_dir / "take_007.wav").touch()

        self.assertEqual(self.manager.get_highest_take("utt_001"), 7)

    def test_get_existing_takes(self):
        """Test getting all existing takes."""
        # Create takes with gaps
        utterance_dir = self.recording_dir / "utt_001"
        utterance_dir.mkdir(parents=True)
        (utterance_dir / "take_001.flac").touch()
        (utterance_dir / "take_003.flac").touch()
        (utterance_dir / "take_007.wav").touch()

        existing = self.manager.get_existing_takes("utt_001")
        self.assertEqual(existing, [1, 3, 7])

    def test_scan_all_takes(self):
        """Test scanning all takes for multiple labels."""
        # Create recordings for different utterances
        for label in ["utt_001", "utt_002", "utt_003"]:
            utterance_dir = self.recording_dir / label
            utterance_dir.mkdir(parents=True)

            if label == "utt_001":
                (utterance_dir / "take_001.flac").touch()
                (utterance_dir / "take_002.flac").touch()
            elif label == "utt_002":
                (utterance_dir / "take_001.wav").touch()

        takes = self.manager.scan_all_takes(["utt_001", "utt_002", "utt_003"])
        self.assertEqual(takes["utt_001"], 2)
        self.assertEqual(takes["utt_002"], 1)
        self.assertEqual(takes["utt_003"], 0)

    def test_directory_structure(self):
        """Test that correct directory structure is created."""
        # Get path for recording - should create directory
        path = self.manager.get_recording_path("utt_001", 1)

        # Check directory was created
        utterance_dir = self.recording_dir / "utt_001"
        self.assertTrue(utterance_dir.exists())
        self.assertTrue(utterance_dir.is_dir())

    def test_load_save_audio(self):
        """Test loading and saving audio files."""
        # Create test audio data (use values in valid range -1 to 1)
        sample_rate = 48000
        duration = 0.5  # seconds
        samples = int(sample_rate * duration)
        audio_data = np.sin(2 * np.pi * 440 * np.arange(samples) / sample_rate).astype(np.float32)
        audio_data = np.clip(audio_data, -1.0, 1.0)  # Ensure within valid range

        # Save audio
        test_file = self.recording_dir / "test.wav"
        self.manager.save_audio(test_file, audio_data, sample_rate, 'PCM_16')  # Use PCM_16 for better compatibility

        # Load audio
        loaded_data, loaded_sr = self.manager.load_audio(test_file)

        self.assertEqual(loaded_sr, sample_rate)
        self.assertEqual(len(loaded_data), len(audio_data))
        # Lower precision due to potential quantization
        np.testing.assert_array_almost_equal(loaded_data, audio_data, decimal=3)


class TestScriptFileManager(unittest.TestCase):
    """Test ScriptFileManager functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_script(self):
        """Test loading and parsing Festival format script."""
        # Create test script
        script_file = self.test_dir / "test.txt"
        script_content = """(utt_001 "This is the first utterance")
(utt_002 "This is the second utterance")
# This is a comment
(utt_003 "Third utterance with quotes")
"""
        script_file.write_text(script_content)

        # Load script
        labels, utterances = ScriptFileManager.load_script(script_file)

        self.assertEqual(len(labels), 3)
        self.assertEqual(labels[0], "utt_001")
        self.assertEqual(utterances[0], "This is the first utterance")
        self.assertEqual(labels[2], "utt_003")
        self.assertEqual(utterances[2], "Third utterance with quotes")

    def test_save_script(self):
        """Test saving script in Festival format."""
        labels = ["utt_001", "utt_002"]
        utterances = ["First utterance", "Second utterance"]

        script_file = self.test_dir / "output.txt"
        ScriptFileManager.save_script(script_file, labels, utterances)

        # Read back and verify
        content = script_file.read_text()
        lines = content.strip().split('\n')

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], '(utt_001 "First utterance")')
        self.assertEqual(lines[1], '(utt_002 "Second utterance")')

    def test_validate_script(self):
        """Test script validation."""
        # Valid script
        valid_script = self.test_dir / "valid.txt"
        valid_script.write_text('(utt_001 "Test")')

        is_valid, errors = ScriptFileManager.validate_script(valid_script)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Non-existent script
        missing_script = self.test_dir / "missing.txt"
        is_valid, errors = ScriptFileManager.validate_script(missing_script)
        self.assertFalse(is_valid)
        self.assertIn("Script file does not exist", errors[0])

        # Empty script
        empty_script = self.test_dir / "empty.txt"
        empty_script.write_text("")

        is_valid, errors = ScriptFileManager.validate_script(empty_script)
        self.assertFalse(is_valid)

    def test_invalid_format(self):
        """Test handling of invalid script format."""
        # Script with invalid lines
        script_file = self.test_dir / "invalid.txt"
        script_content = """(utt_001 "Valid line")
Invalid line without parentheses
(utt_002 Missing quotes)
(utt_003 "Another valid line")
"""
        script_file.write_text(script_content)

        # Should skip invalid lines but still parse lines with warnings
        labels, utterances = ScriptFileManager.load_script(script_file)

        self.assertEqual(len(labels), 3)  # Valid lines + line with warning
        self.assertEqual(labels[0], "utt_001")
        self.assertEqual(labels[1], "utt_002")  # Parsed despite warning
        self.assertEqual(labels[2], "utt_003")


if __name__ == '__main__':
    unittest.main()