"""Session manager for handling session lifecycle.

This module provides the SessionManager class which handles creating,
loading, and managing recording sessions.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import shutil
import sounddevice as sd

from .models import Session, SessionConfig, SpeakerInfo


class SessionManager:
    """Manages recording sessions.

    Handles session creation, loading, validation, and provides
    utilities for session management.
    """

    SUFFIX = ".revoxx"
    SESSION_FILE = "session.json"
    SCRIPT_FILE = "script.txt"

    def __init__(self, settings_file: Optional[Path] = None):
        """Initialize session manager.

        Args:
            settings_file: Path to global settings file for recent sessions
        """
        self.settings_file = settings_file or Path.home() / ".revoxx" / "settings.json"
        self.current_session: Optional[Session] = None

    def create_session(
        self,
        base_dir: Path,
        speaker_name: str,
        gender: str,
        emotion: str,
        audio_config: SessionConfig,
        script_source: Path,
        custom_dir_name: Optional[str] = None,
    ) -> Session:
        """Create a new session.

        Args:
            base_dir: Base directory for sessions
            speaker_name: Name of the speaker
            gender: Gender (M/F/Other)
            emotion: Emotion being recorded
            audio_config: Audio configuration for the session
            script_source: Path to script file to copy (required)
            custom_dir_name: Optional custom directory name

        Returns:
            Created session instance

        Raises:
            FileExistsError: If session directory already exists
            FileNotFoundError: If script file doesn't exist
            ValueError: If script file is invalid
        """
        # Generate directory name
        if custom_dir_name:
            dir_name = custom_dir_name
        else:
            dir_name = f"{speaker_name.lower()}_{emotion}"

        # Ensure .revoxx suffix
        if not dir_name.endswith(self.SUFFIX):
            dir_name += self.SUFFIX

        session_dir = base_dir / dir_name

        # Check if already exists
        if session_dir.exists():
            raise FileExistsError(f"Session directory already exists: {session_dir}")

        # Validate script file
        if not script_source:
            raise ValueError("Script file is required for creating a session")
        if not script_source.exists():
            raise FileNotFoundError(f"Script file not found: {script_source}")
        if not script_source.is_file():
            raise ValueError(f"Script path is not a file: {script_source}")

        # Create directory structure
        session_dir.mkdir(parents=True)
        (session_dir / "recordings").mkdir()
        (session_dir / "trash").mkdir()
        (session_dir / "exports").mkdir()

        # Copy script file (required)
        shutil.copy(script_source, session_dir / self.SCRIPT_FILE)

        # Create session object
        speaker = SpeakerInfo(
            id=f"speaker_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=speaker_name,
            gender=gender,
            emotion=emotion,
        )

        session = Session(
            name=f"{speaker_name} {emotion.title()} Session",
            speaker=speaker,
            audio_config=audio_config,
            created_at=datetime.now(),
            modified_at=datetime.now(),
            session_dir=session_dir,
        )

        # Save session
        session.save()

        # Update recent sessions and default base dir
        self._add_to_recent_sessions(session_dir)
        self.set_default_base_dir(base_dir)

        self.current_session = session
        return session

    def load_session(self, session_dir: Path) -> Session:
        """Load an existing session.

        Args:
            session_dir: Path to session directory

        Returns:
            Loaded session instance

        Raises:
            FileNotFoundError: If session doesn't exist or script file is missing
            ValueError: If session is invalid
        """

        if not session_dir.exists():
            raise FileNotFoundError(f"Session directory not found: {session_dir}")

        if not session_dir.is_dir():
            raise ValueError(f"Not a directory: {session_dir}")

        # Check for .revoxx suffix
        if not session_dir.name.endswith(self.SUFFIX):
            raise ValueError(
                f"Not a valid session directory (missing {self.SUFFIX}): {session_dir}"
            )

        # Check for script file
        script_path = session_dir / self.SCRIPT_FILE
        if not script_path.exists():
            raise FileNotFoundError(
                f"Required script file not found in session: {script_path}"
            )

        session = Session.load(session_dir)

        # Validate audio configuration against current device
        if session.audio_config:
            self._validate_audio_config(session.audio_config)

        # Update recent sessions
        self._add_to_recent_sessions(session_dir)

        self.current_session = session
        return session

    def find_sessions(self, search_dir: Path) -> List[Path]:
        """Find all session directories in a given directory.

        Args:
            search_dir: Directory to search in

        Returns:
            List of session directory paths
        """
        sessions = []
        if search_dir.exists():
            sessions = sorted(
                [
                    d
                    for d in search_dir.iterdir()
                    if d.is_dir() and d.name.endswith(self.SUFFIX)
                ]
            )
        return sessions

    def get_recent_sessions(self, max_count: int = 10) -> List[Path]:
        """Get list of recently used sessions.

        Args:
            max_count: Maximum number of recent sessions to return

        Returns:
            List of session paths
        """
        if not self.settings_file.exists():
            return []

        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                recent = settings.get("recent_sessions", [])
                # Filter out non-existent paths
                valid_recent = [Path(p) for p in recent[:max_count] if Path(p).exists()]
                return valid_recent
        except (json.JSONDecodeError, IOError):
            return []

    def get_last_session(self) -> Optional[Path]:
        """Get the last used session path.

        Returns:
            Path to last session or None
        """
        if not self.settings_file.exists():
            return None

        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                last_path = settings.get("last_session_path")
                if last_path and Path(last_path).exists():
                    return Path(last_path)
        except (json.JSONDecodeError, IOError):
            pass

        return None

    def validate_session(self, session_dir: Path) -> Dict[str, Any]:
        """Validate a session directory.

        Args:
            session_dir: Path to session directory

        Returns:
            Dictionary with validation results
        """
        result = {"valid": True, "errors": [], "warnings": []}

        # Check directory exists
        if not session_dir.exists():
            result["valid"] = False
            result["errors"].append(f"Directory not found: {session_dir}")
            return result

        # Check for session.json
        session_file = session_dir / self.SESSION_FILE
        if not session_file.exists():
            result["valid"] = False
            result["errors"].append("Missing session.json")
            return result

        # Try to load session
        try:
            Session.load(session_dir)
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Failed to load session: {e}")
            return result

        # Check required directories
        for subdir in ["recordings", "trash"]:
            if not (session_dir / subdir).exists():
                result["warnings"].append(f"Missing {subdir} directory")

        # Check script file
        script_file = session_dir / self.SCRIPT_FILE
        if not script_file.exists():
            result["valid"] = False
            result["errors"].append(
                f"Required script file not found: {self.SCRIPT_FILE}"
            )

        return result

    def get_compatible_devices(
        self, audio_config: SessionConfig
    ) -> List[Dict[str, Any]]:
        """Get list of compatible audio devices for given configuration.

        Args:
            audio_config: Audio configuration to check against

        Returns:
            List of compatible device info dictionaries
        """
        compatible = []
        devices = sd.query_devices()

        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:  # Input device
                device_info = dict(device)
                device_info["index"] = i
                if audio_config.is_compatible_with_device(device_info):
                    compatible.append(device_info)

        return compatible

    def _validate_audio_config(self, audio_config: SessionConfig) -> None:
        """Validate audio configuration against available devices.

        Args:
            audio_config: Configuration to validate

        Raises:
            ValueError: If no compatible device found
        """

        # First check if configured device is valid
        if audio_config.validate_device():
            return

        # Device not compatible, try to find alternative
        compatible_device = audio_config.find_compatible_device()

        if compatible_device:
            # We could optionally update the config here or just warn the user
            # For now, just log it
            return

        # No compatible device found at all
        raise ValueError(
            f"No audio device found that supports "
            f"{audio_config.sample_rate}Hz/{audio_config.bit_depth}bit"
        )

    def _add_to_recent_sessions(self, session_dir: Path) -> None:
        """Add session to recent sessions list.

        Args:
            session_dir: Path to session directory
        """
        # Load existing settings
        settings = {}
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                settings = {}

        # Update recent sessions
        recent = settings.get("recent_sessions", [])
        session_path = str(session_dir.absolute())

        # Remove if already in list
        if session_path in recent:
            recent.remove(session_path)

        # Add to front
        recent.insert(0, session_path)

        # Limit to 10
        recent = recent[:10]

        # Update settings
        settings["recent_sessions"] = recent
        settings["last_session_path"] = session_path

        # Save settings
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.settings_file, "w") as f:
            json.dump(settings, f, indent=2)

    def get_default_base_dir(self) -> Optional[Path]:
        """Get the default base directory for new sessions.

        Returns:
            Default base directory or None
        """
        if not self.settings_file.exists():
            return None

        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                base_dir = settings.get("default_base_dir")
                if base_dir:
                    path = Path(base_dir)
                    if path.exists():
                        return path
        except (json.JSONDecodeError, IOError):
            pass

        return None

    def set_default_base_dir(self, base_dir: Path) -> None:
        """Set the default base directory for new sessions.

        Args:
            base_dir: Directory to use as default for new sessions
        """
        # Load existing settings
        settings = {}
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                settings = {}

        # Update default base dir
        settings["default_base_dir"] = str(base_dir.absolute())

        # Save settings
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.settings_file, "w") as f:
            json.dump(settings, f, indent=2)
