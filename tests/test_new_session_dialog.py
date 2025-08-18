"""Tests for the New Session Dialog."""

import unittest
import tkinter as tk
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from emospeech_recorder.ui.dialogs.new_session_dialog import NewSessionDialog, NewSessionData


class TestNewSessionDialog(unittest.TestCase):
    """Test the New Session Dialog functionality."""

    def setUp(self):
        """Set up test environment."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window
        self.temp_dir = tempfile.mkdtemp()
        self.test_script = Path(self.temp_dir) / "test_script.txt"
        self.test_script.write_text('(utt_001 "Test utterance")')

    def tearDown(self):
        """Clean up test environment."""
        try:
            self.root.destroy()
        except:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dialog_creation(self):
        """Test that dialog is created correctly."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Check that dialog exists
        self.assertIsNotNone(dialog.dialog)
        self.assertEqual(dialog.dialog.title(), "New Session")

        # Check that variables are initialized
        self.assertEqual(dialog.gender_var.get(), "M")
        self.assertEqual(dialog.emotion_var.get(), "neutral")

        # Clean up
        dialog.dialog.destroy()

    def test_validation_empty_fields(self):
        """Test validation with empty required fields."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Try to validate with empty fields
        with patch('tkinter.messagebox.showerror') as mock_error:
            result = dialog._validate_input()
            self.assertFalse(result)
            mock_error.assert_called_once()

            # Check that error message mentions required fields
            error_msg = mock_error.call_args[0][1]
            self.assertIn("Speaker name is required", error_msg)
            self.assertIn("Script file is required", error_msg)

        dialog.dialog.destroy()

    def test_validation_nonexistent_script(self):
        """Test validation with non-existent script file."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Set speaker name and non-existent script path
        dialog.speaker_name_var.set("Test Speaker")
        dialog.script_path_var.set("/nonexistent/script.txt")
        dialog.base_dir_var.set(str(self.temp_dir))

        with patch('tkinter.messagebox.showerror') as mock_error:
            result = dialog._validate_input()
            self.assertFalse(result)
            mock_error.assert_called_once()

            error_msg = mock_error.call_args[0][1]
            self.assertIn("Script file does not exist", error_msg)

        dialog.dialog.destroy()

    def test_successful_data_collection(self):
        """Test successful data collection from dialog."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Set valid data
        dialog.speaker_name_var.set("Test Speaker")
        dialog.gender_var.set("F")
        dialog.emotion_var.set("happy")
        dialog.script_path_var.set(str(self.test_script))
        dialog.base_dir_var.set(str(self.temp_dir))
        dialog.custom_dir_var.set("custom_session")

        # Simulate OK button click
        dialog._on_ok()

        # Check result
        self.assertIsNotNone(dialog.result)
        self.assertEqual(dialog.result.speaker_name, "Test Speaker")
        self.assertEqual(dialog.result.gender, "F")
        self.assertEqual(dialog.result.emotion, "happy")
        self.assertEqual(dialog.result.script_path, self.test_script)
        self.assertEqual(dialog.result.base_dir, Path(self.temp_dir))
        self.assertEqual(dialog.result.custom_dir_name, "custom_session")

    def test_cancel_returns_none(self):
        """Test that cancelling returns None."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Simulate Cancel button click
        dialog._on_cancel()

        # Check result
        self.assertIsNone(dialog.result)

    def test_empty_custom_dir_is_none(self):
        """Test that empty custom directory becomes None."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Set valid data with empty custom dir
        dialog.speaker_name_var.set("Test Speaker")
        dialog.script_path_var.set(str(self.test_script))
        dialog.base_dir_var.set(str(self.temp_dir))
        dialog.custom_dir_var.set("")  # Empty custom dir

        dialog._on_ok()

        # Check that custom_dir_name is None
        self.assertIsNotNone(dialog.result)
        self.assertIsNone(dialog.result.custom_dir_name)

    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed from inputs."""
        dialog = NewSessionDialog(self.root, Path(self.temp_dir))

        # Set data with extra whitespace
        dialog.speaker_name_var.set("  Test Speaker  ")
        dialog.script_path_var.set(str(self.test_script))
        dialog.base_dir_var.set(str(self.temp_dir))
        dialog.custom_dir_var.set("  custom  ")

        dialog._on_ok()

        # Check trimmed values
        self.assertEqual(dialog.result.speaker_name, "Test Speaker")
        self.assertEqual(dialog.result.custom_dir_name, "custom")


if __name__ == '__main__':
    unittest.main()