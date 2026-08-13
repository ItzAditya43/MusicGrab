"""Configuration management for MusicGrab."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Manages MusicGrab configuration and settings."""

    DEFAULT_CONFIG_DIR = Path.home() / ".config" / "musicgrab"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
    DEFAULT_DOWNLOAD_DIR = Path.home() / "Music"
    DEFAULT_LIBRARY_DIR = Path.home() / "Music" / "MusicGrab"

    def __init__(self, config_file: Optional[Path] = None) -> None:
        self.config_file = config_file or self.DEFAULT_CONFIG_FILE
        self.download_dir = self.DEFAULT_DOWNLOAD_DIR
        self.library_dir = self.DEFAULT_LIBRARY_DIR
        self.audio_format = "mp3"
        self.audio_quality = "320"
        self.embed_artwork = True
        self.embed_metadata = True
        self.save_artwork = True
        self.overwrite = False
        self._load()

    def _load(self) -> None:
        """Load configuration from file if it exists."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                self.download_dir = Path(data.get("download_dir", str(self.download_dir)))
                self.library_dir = Path(data.get("library_dir", str(self.library_dir)))
                self.audio_format = data.get("audio_format", self.audio_format)
                self.audio_quality = data.get("audio_quality", self.audio_quality)
                self.embed_artwork = data.get("embed_artwork", self.embed_artwork)
                self.embed_metadata = data.get("embed_metadata", self.embed_metadata)
                self.save_artwork = data.get("save_artwork", self.save_artwork)
                self.overwrite = data.get("overwrite", self.overwrite)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        """Save current configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {
            "download_dir": str(self.download_dir),
            "library_dir": str(self.library_dir),
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "embed_artwork": self.embed_artwork,
            "embed_metadata": self.embed_metadata,
            "save_artwork": self.save_artwork,
            "overwrite": self.overwrite,
        }
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=2)

    def ensure_dirs(self) -> None:
        """Ensure download and library directories exist."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global config instance."""
    return config


def set_download_dir(path: str) -> None:
    """Set the download directory."""
    config.download_dir = Path(path)
    config.save()


def set_library_dir(path: str) -> None:
    """Set the library directory."""
    config.library_dir = Path(path)
    config.save()


