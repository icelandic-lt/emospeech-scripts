"""Data models for session management.

This module defines the core data structures used in session management,
including Session, SessionConfig, and SpeakerInfo.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
import json


@dataclass
class SpeakerInfo:
    """Information about the speaker in a session."""

    id: str
    name: str
    gender: str  # M/F/Other
    emotion: str  # neutral/happy/sad/angry/etc
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpeakerInfo':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class SessionConfig:
    """Audio configuration for a session.

    These settings are locked after session creation to ensure
    consistency across all recordings.
    """

    sample_rate: int
    bit_depth: int
    format: str  # wav/flac
    input_device: Optional[str] = None
    channels: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionConfig':
        """Create instance from dictionary."""
        return cls(**data)

    def is_compatible_with_device(self, device_info: Dict[str, Any]) -> bool:
        """Check if device supports this configuration.

        Args:
            device_info: Device information from sounddevice

        Returns:
            True if device can support these settings
        """
        # Check sample rate support
        if 'default_samplerate' in device_info:
            # Simple check - could be enhanced with actual testing
            device_sr = device_info['default_samplerate']
            if device_sr and abs(device_sr - self.sample_rate) > 1:
                return False

        # Check channel support
        max_channels = device_info.get('max_input_channels', 0)
        if max_channels < self.channels:
            return False

        return True


@dataclass
class Session:
    """Represents a recording session.

    A session encapsulates all data for a recording series including
    configuration, speaker info, and file paths.
    """

    version: str = "1.0"
    name: str = ""
    speaker: Optional[SpeakerInfo] = None
    audio_config: Optional[SessionConfig] = None
    script_path: str = "script.txt"
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    session_dir: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            'version': self.version,
            'name': self.name,
            'script_path': self.script_path
        }

        if self.speaker:
            data['speaker'] = self.speaker.to_dict()

        if self.audio_config:
            data['audio_config'] = self.audio_config.to_dict()

        if self.created_at:
            data['created_at'] = self.created_at.isoformat()

        if self.modified_at:
            data['modified_at'] = self.modified_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], session_dir: Optional[Path] = None) -> 'Session':
        """Create instance from dictionary.

        Args:
            data: Dictionary with session data
            session_dir: Path to session directory

        Returns:
            Session instance
        """
        session = cls(
            version=data.get('version', '1.0'),
            name=data.get('name', ''),
            script_path=data.get('script_path', 'script.txt'),
            session_dir=session_dir
        )

        if 'speaker' in data:
            session.speaker = SpeakerInfo.from_dict(data['speaker'])

        if 'audio_config' in data:
            session.audio_config = SessionConfig.from_dict(data['audio_config'])

        if 'created_at' in data:
            session.created_at = datetime.fromisoformat(data['created_at'])

        if 'modified_at' in data:
            session.modified_at = datetime.fromisoformat(data['modified_at'])

        return session

    def save(self, session_dir: Optional[Path] = None) -> None:
        """Save session to JSON file.

        Args:
            session_dir: Directory to save to (uses self.session_dir if None)
        """
        save_dir = session_dir or self.session_dir
        if not save_dir:
            raise ValueError("No session directory specified")

        self.modified_at = datetime.now()

        session_file = save_dir / "session.json"
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, session_dir: Path) -> 'Session':
        """Load session from directory.

        Args:
            session_dir: Path to session directory

        Returns:
            Loaded session instance

        Raises:
            FileNotFoundError: If session.json doesn't exist
            json.JSONDecodeError: If session.json is invalid
        """
        session_file = session_dir / "session.json"
        if not session_file.exists():
            raise FileNotFoundError(f"No session.json found in {session_dir}")

        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return cls.from_dict(data, session_dir)

    def get_recordings_dir(self) -> Path:
        """Get path to recordings directory."""
        if not self.session_dir:
            raise ValueError("Session directory not set")
        return self.session_dir / "recordings"

    def get_trash_dir(self) -> Path:
        """Get path to trash directory."""
        if not self.session_dir:
            raise ValueError("Session directory not set")
        return self.session_dir / "trash"

    def get_script_path(self) -> Path:
        """Get full path to script file."""
        if not self.session_dir:
            raise ValueError("Session directory not set")
        return self.session_dir / self.script_path