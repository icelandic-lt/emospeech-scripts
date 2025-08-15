"""Tests for session data models.

Tests the Session, SessionConfig, and SpeakerInfo classes
for proper serialization, deserialization, and validation.
"""

import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime

from emospeech_recorder.session.models import Session, SessionConfig, SpeakerInfo


class TestSpeakerInfo(unittest.TestCase):
    """Test SpeakerInfo data model."""

    def test_create_speaker(self):
        """Test creating a speaker instance."""
        speaker = SpeakerInfo(
            id="speaker_001",
            name="Anna",
            gender="F",
            emotion="happy"
        )

        self.assertEqual(speaker.id, "speaker_001")
        self.assertEqual(speaker.name, "Anna")
        self.assertEqual(speaker.gender, "F")
        self.assertEqual(speaker.emotion, "happy")
        self.assertEqual(speaker.metadata, {})

    def test_speaker_with_metadata(self):
        """Test speaker with additional metadata."""
        speaker = SpeakerInfo(
            id="speaker_001",
            name="Anna",
            gender="F",
            emotion="happy",
            metadata={"age": 35, "dialect": "Reykjavik"}
        )

        self.assertEqual(speaker.metadata["age"], 35)
        self.assertEqual(speaker.metadata["dialect"], "Reykjavik")

    def test_speaker_serialization(self):
        """Test converting speaker to/from dictionary."""
        speaker = SpeakerInfo(
            id="speaker_001",
            name="Anna",
            gender="F",
            emotion="happy",
            metadata={"age": 35}
        )

        # To dict
        data = speaker.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "Anna")
        self.assertEqual(data["metadata"]["age"], 35)

        # From dict
        speaker2 = SpeakerInfo.from_dict(data)
        self.assertEqual(speaker2.name, speaker.name)
        self.assertEqual(speaker2.metadata, speaker.metadata)


class TestSessionConfig(unittest.TestCase):
    """Test SessionConfig data model."""

    def test_create_config(self):
        """Test creating audio configuration."""
        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav"
        )

        self.assertEqual(config.sample_rate, 48000)
        self.assertEqual(config.bit_depth, 24)
        self.assertEqual(config.format, "wav")
        self.assertEqual(config.channels, 1)  # Default
        self.assertIsNone(config.input_device)

    def test_config_with_device(self):
        """Test config with input device specified."""
        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav",
            input_device="Scarlett 2i2",
            channels=2
        )

        self.assertEqual(config.input_device, "Scarlett 2i2")
        self.assertEqual(config.channels, 2)

    def test_config_serialization(self):
        """Test converting config to/from dictionary."""
        config = SessionConfig(
            sample_rate=96000,
            bit_depth=32,
            format="flac",
            input_device="RME"
        )

        # To dict
        data = config.to_dict()
        self.assertEqual(data["sample_rate"], 96000)
        self.assertEqual(data["format"], "flac")

        # From dict
        config2 = SessionConfig.from_dict(data)
        self.assertEqual(config2.sample_rate, config.sample_rate)
        self.assertEqual(config2.input_device, config.input_device)

    def test_device_compatibility(self):
        """Test device compatibility checking."""
        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav",
            channels=2
        )

        # Compatible device
        device_info = {
            'default_samplerate': 48000,
            'max_input_channels': 4
        }
        self.assertTrue(config.is_compatible_with_device(device_info))

        # Incompatible sample rate
        device_info = {
            'default_samplerate': 44100,
            'max_input_channels': 4
        }
        self.assertFalse(config.is_compatible_with_device(device_info))

        # Incompatible channels
        device_info = {
            'default_samplerate': 48000,
            'max_input_channels': 1
        }
        self.assertFalse(config.is_compatible_with_device(device_info))


class TestSession(unittest.TestCase):
    """Test Session data model."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_dir = Path(self.temp_dir) / "test_session.revoxx"
        self.session_dir.mkdir()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_empty_session(self):
        """Test creating minimal session."""
        session = Session()

        self.assertEqual(session.version, "1.0")
        self.assertEqual(session.name, "")
        self.assertIsNone(session.speaker)
        self.assertIsNone(session.audio_config)
        self.assertEqual(session.script_path, "script.txt")

    def test_create_full_session(self):
        """Test creating session with all fields."""
        speaker = SpeakerInfo(
            id="speaker_001",
            name="Anna",
            gender="F",
            emotion="happy"
        )

        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav"
        )

        session = Session(
            name="Test Session",
            speaker=speaker,
            audio_config=config,
            created_at=datetime.now(),
            session_dir=self.session_dir
        )

        self.assertEqual(session.name, "Test Session")
        self.assertEqual(session.speaker.name, "Anna")
        self.assertEqual(session.audio_config.sample_rate, 48000)
        self.assertIsNotNone(session.created_at)
        self.assertEqual(session.session_dir, self.session_dir)

    def test_session_paths(self):
        """Test getting session directory paths."""
        session = Session(session_dir=self.session_dir)

        # Test path methods
        recordings_dir = session.get_recordings_dir()
        self.assertEqual(recordings_dir, self.session_dir / "recordings")

        trash_dir = session.get_trash_dir()
        self.assertEqual(trash_dir, self.session_dir / "trash")

        script_path = session.get_script_path()
        self.assertEqual(script_path, self.session_dir / "script.txt")

    def test_session_paths_without_dir(self):
        """Test path methods raise error without session_dir."""
        session = Session()

        with self.assertRaises(ValueError):
            session.get_recordings_dir()

        with self.assertRaises(ValueError):
            session.get_trash_dir()

        with self.assertRaises(ValueError):
            session.get_script_path()

    def test_save_and_load(self):
        """Test saving and loading session from disk."""
        # Create session
        speaker = SpeakerInfo(
            id="speaker_001",
            name="Test Speaker",
            gender="M",
            emotion="neutral"
        )

        config = SessionConfig(
            sample_rate=44100,
            bit_depth=16,
            format="wav"
        )

        session = Session(
            name="Save Test",
            speaker=speaker,
            audio_config=config,
            created_at=datetime.now(),
            session_dir=self.session_dir
        )

        # Save
        session.save()

        # Verify file exists
        session_file = self.session_dir / "session.json"
        self.assertTrue(session_file.exists())

        # Load
        loaded = Session.load(self.session_dir)

        # Verify loaded data
        self.assertEqual(loaded.name, "Save Test")
        self.assertEqual(loaded.speaker.name, "Test Speaker")
        self.assertEqual(loaded.audio_config.sample_rate, 44100)
        self.assertIsNotNone(loaded.modified_at)
        self.assertEqual(loaded.session_dir, self.session_dir)

    def test_load_nonexistent(self):
        """Test loading from non-existent directory."""
        bad_dir = Path(self.temp_dir) / "nonexistent"

        with self.assertRaises(FileNotFoundError):
            Session.load(bad_dir)

    def test_json_serialization(self):
        """Test JSON serialization round-trip."""
        speaker = SpeakerInfo(
            id="speaker_001",
            name="JSON Test",
            gender="F",
            emotion="sad",
            metadata={"test": "value"}
        )

        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="flac"
        )

        session = Session(
            name="JSON Session",
            speaker=speaker,
            audio_config=config,
            created_at=datetime.now()
        )

        # To JSON
        data = session.to_dict()
        json_str = json.dumps(data)

        # From JSON
        loaded_data = json.loads(json_str)
        loaded_session = Session.from_dict(loaded_data)

        # Verify
        self.assertEqual(loaded_session.name, "JSON Session")
        self.assertEqual(loaded_session.speaker.name, "JSON Test")
        self.assertEqual(loaded_session.speaker.metadata["test"], "value")
        self.assertEqual(loaded_session.audio_config.format, "flac")


if __name__ == '__main__':
    unittest.main()