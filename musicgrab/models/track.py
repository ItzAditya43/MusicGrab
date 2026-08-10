"""Track data model for MusicGrab."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Track:
    """Represents a single music track."""

    title: str
    artist: str
    album: str = ""
    duration: float = 0.0
    track_number: int = 0
    disc_number: int = 0
    year: int = 0
    genre: str = ""
    isrc: str = ""
    source: str = ""  # "youtube" or "spotify"
    source_url: str = ""
    source_id: str = ""
    thumbnail_url: str = ""
    thumbnail_data: bytes = b""
    output_path: Optional[Path] = None
    downloaded: bool = False
    file_size: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        """Get a display-friendly title."""
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title

    @property
    def filename(self) -> str:
        """Generate a safe filename for this track."""
        from musicgrab.utils import sanitize_filename

        if self.artist and self.title:
            name = f"{self.artist} - {self.title}"
        else:
            name = self.title or "unknown"
        return sanitize_filename(name)

    def to_dict(self) -> dict:
        """Convert track to a dictionary."""
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "track_number": self.track_number,
            "disc_number": self.disc_number,
            "year": self.year,
            "genre": self.genre,
            "isrc": self.isrc,
            "source": self.source,
            "source_url": self.source_url,
            "source_id": self.source_id,
            "thumbnail_url": self.thumbnail_url,
            "output_path": str(self.output_path) if self.output_path else None,
            "downloaded": self.downloaded,
            "file_size": self.file_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        """Create a Track from a dictionary."""
        return cls(
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            duration=data.get("duration", 0.0),
            track_number=data.get("track_number", 0),
            disc_number=data.get("disc_number", 0),
            year=data.get("year", 0),
            genre=data.get("genre", ""),
            isrc=data.get("isrc", ""),
            source=data.get("source", ""),
            source_url=data.get("source_url", ""),
            source_id=data.get("source_id", ""),
            thumbnail_url=data.get("thumbnail_url", ""),
            output_path=Path(data["output_path"]) if data.get("output_path") else None,
            downloaded=data.get("downloaded", False),
            file_size=data.get("file_size", 0.0),
        )
