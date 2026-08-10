"""Playlist data model for MusicGrab."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from musicgrab.models.track import Track


@dataclass
class Playlist:
    """Represents a music playlist or collection of tracks."""

    title: str
    source: str = ""  # "youtube" or "spotify"
    source_url: str = ""
    source_id: str = ""
    description: str = ""
    tracks: List["Track"] = field(default_factory=list)
    thumbnail_url: str = ""
    owner: str = ""
    total_tracks: int = 0

    @property
    def track_count(self) -> int:
        """Get the number of tracks in the playlist."""
        return len(self.tracks)

    @property
    def downloaded_count(self) -> int:
        """Get the number of downloaded tracks."""
        return sum(1 for t in self.tracks if t.downloaded)

    @property
    def is_complete(self) -> bool:
        """Check if all tracks are downloaded."""
        return self.downloaded_count == self.track_count

    def add_track(self, track: "Track") -> None:
        """Add a track to the playlist."""
        self.tracks.append(track)
        self.total_tracks = len(self.tracks)

    def get_track(self, index: int) -> Optional["Track"]:
        """Get a track by index."""
        if 0 <= index < len(self.tracks):
            return self.tracks[index]
        return None

    def to_dict(self) -> dict:
        """Convert playlist to a dictionary."""
        return {
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "source_id": self.source_id,
            "description": self.description,
            "tracks": [t.to_dict() for t in self.tracks],
            "thumbnail_url": self.thumbnail_url,
            "owner": self.owner,
            "total_tracks": self.total_tracks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Playlist":
        """Create a Playlist from a dictionary."""
        from musicgrab.models.track import Track

        return cls(
            title=data.get("title", ""),
            source=data.get("source", ""),
            source_url=data.get("source_url", ""),
            source_id=data.get("source_id", ""),
            description=data.get("description", ""),
            tracks=[Track.from_dict(t) for t in data.get("tracks", [])],
            thumbnail_url=data.get("thumbnail_url", ""),
            owner=data.get("owner", ""),
            total_tracks=data.get("total_tracks", 0),
        )
