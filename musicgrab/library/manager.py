"""Local music library manager for MusicGrab.

Manages a local music library, including scanning for tracks,
organizing files, and maintaining a library database.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from musicgrab.models.track import Track
from musicgrab.utils import (
    console,
    format_duration,
    format_file_size,
    print_error,
    print_info,
    print_success,
    print_warning,
    sanitize_filename,
    sanitize_path_component,
)


def _is_under(path_str: str, dir_str: str) -> bool:
    """Whether the resolved path lies inside the resolved directory."""
    try:
        Path(path_str).resolve().relative_to(dir_str)
        return True
    except ValueError:
        return False


class LibraryManager:
    """Manages the local music library."""

    AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".wma"}

    def __init__(self, config) -> None:
        self.config = config
        self.library_dir = config.library_dir
        self.library_file = self.library_dir / "library.json"
        self._library_data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load the library database."""
        if self.library_file.exists():
            try:
                with open(self.library_file, "r") as f:
                    self._library_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._library_data = {"tracks": [], "last_scan": None}
        else:
            self._library_data = {"tracks": [], "last_scan": None}

    def _save(self) -> None:
        """Save the library database."""
        self.library_dir.mkdir(parents=True, exist_ok=True)
        with open(self.library_file, "w") as f:
            json.dump(self._library_data, f, indent=2)

    def scan(self, directory: Optional[Path] = None) -> List[Track]:
        """Scan a directory for audio files and add them to the library.

        Args:
            directory: Directory to scan. Defaults to the library directory.

        Returns:
            List of discovered Track objects.
        """
        scan_dir = directory or self.library_dir
        if not scan_dir.exists():
            print_error(f"Directory does not exist: {scan_dir}")
            return []

        print_info(f"Scanning: {scan_dir}")
        tracks = []

        for root, dirs, files in os.walk(scan_dir):
            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in self.AUDIO_EXTENSIONS:
                    track = self._scan_file(file_path)
                    if track:
                        tracks.append(track)

        # Merge into library data: replace entries for files under scan_dir,
        # but leave tracks located elsewhere untouched (a scan of one
        # directory must never delete knowledge of tracks in another).
        scan_dir_resolved = str(scan_dir.resolve())
        existing = self._library_data.get("tracks", [])
        kept = [
            t for t in existing
            if not (t.get("output_path") and _is_under(t["output_path"], scan_dir_resolved))
        ]
        self._library_data["tracks"] = kept + [t.to_dict() for t in tracks]
        self._library_data["last_scan"] = datetime.now().isoformat()
        self._save()

        print_success(f"Found {len(tracks)} tracks in library")
        return tracks

    def _scan_file(self, file_path: Path) -> Optional[Track]:
        """Scan a single audio file and extract metadata."""
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(file_path)
            if audio is None:
                return None

            # Extract metadata based on file type
            title = ""
            artist = ""
            album = ""
            duration = 0.0
            track_number = 0
            year = 0
            genre = ""

            if file_path.suffix.lower() == ".mp3":
                if audio.tags:
                    title = str(audio.tags.get("TIT2", [""])[0]) if "TIT2" in audio.tags else ""
                    artist = str(audio.tags.get("TPE1", [""])[0]) if "TPE1" in audio.tags else ""
                    album = str(audio.tags.get("TALB", [""])[0]) if "TALB" in audio.tags else ""
                    track_number = int(str(audio.tags.get("TRCK", ["0"])[0])) if "TRCK" in audio.tags else 0
                    year = int(str(audio.tags.get("TDRC", ["0"])[0])) if "TDRC" in audio.tags else 0
                    genre = str(audio.tags.get("TCON", [""])[0]) if "TCON" in audio.tags else ""
            elif file_path.suffix.lower() == ".flac":
                title = audio.get("title", [""])[0] if "title" in audio else ""
                artist = audio.get("artist", [""])[0] if "artist" in audio else ""
                album = audio.get("album", [""])[0] if "album" in audio else ""
                track_number = int(audio.get("tracknumber", ["0"])[0]) if "tracknumber" in audio else 0
                year = int(audio.get("date", ["0"])[0]) if "date" in audio else 0
                genre = audio.get("genre", [""])[0] if "genre" in audio else ""
            elif file_path.suffix.lower() == ".m4a":
                title = str(audio.get("\xa9nam", [""])[0]) if "\xa9nam" in audio else ""
                artist = str(audio.get("\xa9ART", [""])[0]) if "\xa9ART" in audio else ""
                album = str(audio.get("\xa9alb", [""])[0]) if "\xa9alb" in audio else ""
                year = int(str(audio.get("\xa9day", ["0"])[0])) if "\xa9day" in audio else 0
                genre = str(audio.get("\xa9gen", [""])[0]) if "\xa9gen" in audio else ""

            duration = audio.info.length if audio.info else 0.0

            return Track(
                title=title or file_path.stem,
                artist=artist or "Unknown",
                album=album,
                duration=duration,
                track_number=track_number,
                year=year,
                genre=genre,
                source="local",
                source_url=str(file_path),
                source_id=file_path.stem,
                output_path=file_path,
                downloaded=True,
                file_size=file_path.stat().st_size,
            )
        except Exception as e:
            print_warning(f"Could not read metadata from {file_path.name}: {e}")
            return None

    def add_track(self, track: Track) -> None:
        """Add a track to the library."""
        track_data = track.to_dict()
        # Check if already in library
        for existing in self._library_data["tracks"]:
            if existing.get("source_id") == track.source_id and existing.get("source") == track.source:
                return
        self._library_data["tracks"].append(track_data)
        self._save()

    def remove_track(self, track_id: str) -> bool:
        """Remove a track from the library by source ID."""
        tracks = self._library_data["tracks"]
        for i, t in enumerate(tracks):
            if t.get("source_id") == track_id:
                tracks.pop(i)
                self._save()
                return True
        return False

    def list_tracks(self) -> List[Track]:
        """List all tracks in the library."""
        return [Track.from_dict(t) for t in self._library_data.get("tracks", [])]

    def search(self, query: str) -> List[Track]:
        """Search for tracks in the library by title or artist."""
        query_lower = query.lower()
        results = []
        for t in self._library_data.get("tracks", []):
            if query_lower in t.get("title", "").lower() or query_lower in t.get("artist", "").lower():
                results.append(Track.from_dict(t))
        return results

    def organize(self, directory: Optional[Path] = None) -> None:
        """Organize tracks in a directory into artist/album structure."""
        target_dir = directory or self.library_dir
        if not target_dir.exists():
            print_error(f"Directory does not exist: {target_dir}")
            return

        moved = 0
        for root, dirs, files in os.walk(target_dir):
            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() not in self.AUDIO_EXTENSIONS:
                    continue

                track = self._scan_file(file_path)
                if not track:
                    continue

                # Build new path: Artist/Album/Track
                artist_dir = sanitize_path_component(track.artist) if track.artist else "Unknown Artist"
                album_dir = sanitize_path_component(track.album) if track.album else "Unknown Album"
                new_dir = target_dir / artist_dir / album_dir
                new_dir.mkdir(parents=True, exist_ok=True)

                new_filename = f"{track.filename}{file_path.suffix}"
                new_path = new_dir / new_filename

                if new_path != file_path:
                    if new_path.exists() and not self.config.overwrite:
                        print_warning(f"Skipping (file exists): {new_path.name}")
                        continue
                    shutil.move(str(file_path), str(new_path))
                    moved += 1

        if moved > 0:
            print_success(f"Organized {moved} tracks")
        else:
            print_info("No files needed organizing")

    def print_library(self) -> None:
        """Print the library contents in a table."""
        from musicgrab.utils import create_table

        tracks = self.list_tracks()
        if not tracks:
            print_info("Library is empty")
            return

        table = create_table(
            "Music Library",
            ["Title", "Artist", "Album", "Duration", "Size"],
        )

        for track in tracks:
            duration_str = format_duration(track.duration)
            size_str = format_file_size(track.file_size)
            table.add_row(
                track.title,
                track.artist,
                track.album or "-",
                duration_str,
                size_str,
            )

        console.print(table)

    def get_stats(self) -> dict:
        """Get library statistics."""
        tracks = self.list_tracks()
        total_size = sum(t.file_size for t in tracks)
        artists = set(t.artist for t in tracks if t.artist)
        albums = set(t.album for t in tracks if t.album)

        return {
            "total_tracks": len(tracks),
            "total_artists": len(artists),
            "total_albums": len(albums),
            "total_size": total_size,
            "total_size_formatted": format_file_size(total_size),
            "last_scan": self._library_data.get("last_scan"),
        }

    def print_stats(self) -> None:
        """Print library statistics."""
        stats = self.get_stats()
        from musicgrab.utils import create_table

        table = create_table("Library Statistics", ["Metric", "Value"])
        table.add_row("Total Tracks", str(stats["total_tracks"]))
        table.add_row("Total Artists", str(stats["total_artists"]))
        table.add_row("Total Albums", str(stats["total_albums"]))
        table.add_row("Total Size", stats["total_size_formatted"])
        table.add_row("Last Scan", stats["last_scan"] or "Never")
        console.print(table)
