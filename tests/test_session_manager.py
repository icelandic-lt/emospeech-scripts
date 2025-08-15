"""Tests for SessionManager class.

Tests session creation, loading, validation, and management features.
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from emospeech_recorder.session.manager import SessionManager
from emospeech_recorder.session.models import SessionConfig


class TestSessionManager(unittest.TestCase):
    """Test SessionManager functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.settings_file = self.base_dir / "settings.json"
        self.manager = SessionManager(self.settings_file)

        # Default audio config for tests
        self.audio_config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav"
        )

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_session(self):
        """Test creating a new session."""
        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Test",
            gender="M",
            emotion="happy",
            audio_config=self.audio_config
        )

        # Check session object
        self.assertEqual(session.speaker.name, "Test")
        self.assertEqual(session.speaker.gender, "M")
        self.assertEqual(session.speaker.emotion, "happy")
        self.assertEqual(session.audio_config.sample_rate, 48000)

        # Check directory structure
        session_dir = self.base_dir / "test_happy.revoxx"
        self.assertTrue(session_dir.exists())
        self.assertTrue((session_dir / "recordings").exists())
        self.assertTrue((session_dir / "trash").exists())
        self.assertTrue((session_dir / "exports").exists())
        self.assertTrue((session_dir / "session.json").exists())

    def test_create_session_custom_name(self):
        """Test creating session with custom directory name."""
        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Test",
            gender="F",
            emotion="neutral",
            audio_config=self.audio_config,
            custom_dir_name="my_custom_session"
        )

        # Check custom directory was created
        session_dir = self.base_dir / "my_custom_session.revoxx"
        self.assertTrue(session_dir.exists())
        self.assertEqual(session.session_dir, session_dir)

    def test_create_session_with_script(self):
        """Test creating session with script file."""
        # Create test script
        script_file = self.base_dir / "test_script.txt"
        script_file.write_text("Test utterance 1\nTest utterance 2")

        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Test",
            gender="M",
            emotion="angry",
            audio_config=self.audio_config,
            script_source=script_file
        )

        # Check script was copied
        session_script = session.session_dir / "script.txt"
        self.assertTrue(session_script.exists())
        self.assertEqual(session_script.read_text(), "Test utterance 1\nTest utterance 2")

    def test_create_duplicate_session(self):
        """Test creating duplicate session raises error."""
        # Create first session
        self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Test",
            gender="M",
            emotion="happy",
            audio_config=self.audio_config
        )

        # Try to create duplicate
        with self.assertRaises(FileExistsError):
            self.manager.create_session(
                base_dir=self.base_dir,
                speaker_name="Test",
                gender="M",
                emotion="happy",
                audio_config=self.audio_config
            )

    def test_load_session(self):
        """Test loading an existing session."""
        # Create a session first
        created = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="LoadTest",
            gender="F",
            emotion="sad",
            audio_config=self.audio_config
        )

        # Create new manager and load
        new_manager = SessionManager(self.settings_file)
        loaded = new_manager.load_session(created.session_dir)

        # Verify loaded data
        self.assertEqual(loaded.speaker.name, "LoadTest")
        self.assertEqual(loaded.speaker.emotion, "sad")
        self.assertEqual(loaded.audio_config.sample_rate, 48000)

    def test_load_nonexistent_session(self):
        """Test loading non-existent session raises error."""
        bad_dir = self.base_dir / "nonexistent.revoxx"

        with self.assertRaises(FileNotFoundError):
            self.manager.load_session(bad_dir)

    def test_load_invalid_session(self):
        """Test loading invalid session directory."""
        # Create directory without .revoxx suffix
        bad_dir = self.base_dir / "not_a_session"
        bad_dir.mkdir()

        with self.assertRaises(ValueError):
            self.manager.load_session(bad_dir)

    def test_find_sessions(self):
        """Test finding all sessions in directory."""
        # Create multiple sessions
        for i, emotion in enumerate(["happy", "sad", "angry"]):
            self.manager.create_session(
                base_dir=self.base_dir,
                speaker_name=f"Speaker{i}",
                gender="M",
                emotion=emotion,
                audio_config=self.audio_config
            )

        # Also create non-session directory
        (self.base_dir / "not_a_session").mkdir()

        # Find sessions
        sessions = self.manager.find_sessions(self.base_dir)

        # Should find exactly 3 sessions
        self.assertEqual(len(sessions), 3)
        self.assertTrue(all(s.name.endswith(".revoxx") for s in sessions))

    def test_recent_sessions(self):
        """Test recent sessions tracking."""
        # Create sessions
        session1 = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="First",
            gender="M",
            emotion="happy",
            audio_config=self.audio_config
        )

        session2 = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Second",
            gender="F",
            emotion="sad",
            audio_config=self.audio_config
        )

        # Check recent sessions
        recent = self.manager.get_recent_sessions()
        self.assertEqual(len(recent), 2)
        # Most recent should be first
        self.assertEqual(recent[0], session2.session_dir)
        self.assertEqual(recent[1], session1.session_dir)

    def test_last_session(self):
        """Test getting last used session."""
        # Initially no last session
        self.assertIsNone(self.manager.get_last_session())

        # Create session
        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Last",
            gender="M",
            emotion="neutral",
            audio_config=self.audio_config
        )

        # Should be set as last session
        last = self.manager.get_last_session()
        self.assertEqual(last, session.session_dir)

    def test_validate_session(self):
        """Test session validation."""
        # Create valid session
        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Valid",
            gender="F",
            emotion="happy",
            audio_config=self.audio_config
        )

        # Validate
        result = self.manager.validate_session(session.session_dir)
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['errors']), 0)

        # Remove a directory
        shutil.rmtree(session.session_dir / "recordings")

        # Should have warning but still valid
        result = self.manager.validate_session(session.session_dir)
        self.assertTrue(result['valid'])
        self.assertIn("Missing recordings directory", result['warnings'])

        # Remove session.json
        (session.session_dir / "session.json").unlink()

        # Should be invalid
        result = self.manager.validate_session(session.session_dir)
        self.assertFalse(result['valid'])
        self.assertIn("Missing session.json", result['errors'])

    @patch('sounddevice.query_devices')
    def test_get_compatible_devices(self, mock_query):
        """Test finding compatible audio devices."""
        # Mock device list
        mock_query.return_value = [
            {'name': 'Device1', 'max_input_channels': 2, 'default_samplerate': 48000},
            {'name': 'Device2', 'max_input_channels': 2, 'default_samplerate': 44100},
            {'name': 'Device3', 'max_input_channels': 0, 'default_samplerate': 48000},  # Output only
            {'name': 'Device4', 'max_input_channels': 1, 'default_samplerate': 48000},
        ]

        config = SessionConfig(
            sample_rate=48000,
            bit_depth=24,
            format="wav",
            channels=2
        )

        compatible = self.manager.get_compatible_devices(config)

        # Should find Device1 (matching sample rate and channels)
        self.assertEqual(len(compatible), 1)
        self.assertEqual(compatible[0]['name'], 'Device1')

    def test_recent_sessions_persistence(self):
        """Test recent sessions persist across manager instances."""
        # Create session with first manager
        session = self.manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Persist",
            gender="M",
            emotion="happy",
            audio_config=self.audio_config
        )

        # Create new manager instance
        new_manager = SessionManager(self.settings_file)

        # Should see the recent session
        recent = new_manager.get_recent_sessions()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0], session.session_dir)

        # Should see last session
        last = new_manager.get_last_session()
        self.assertEqual(last, session.session_dir)

    def test_settings_file_creation(self):
        """Test settings file is created if it doesn't exist."""
        # Use non-existent settings file
        new_settings = self.base_dir / "subdir" / "settings.json"
        manager = SessionManager(new_settings)

        # Create session
        manager.create_session(
            base_dir=self.base_dir,
            speaker_name="Settings",
            gender="F",
            emotion="neutral",
            audio_config=self.audio_config
        )

        # Settings file should be created
        self.assertTrue(new_settings.exists())

        # Should contain recent session
        with open(new_settings) as f:
            settings = json.load(f)
            self.assertIn('recent_sessions', settings)
            self.assertIn('last_session_path', settings)


if __name__ == '__main__':
    unittest.main()