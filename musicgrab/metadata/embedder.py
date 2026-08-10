"""Metadata embedding module for MusicGrab.

Uses mutagen to embed metadata (ID3 tags) into audio files.
"""

from pathlib import Path
from typing import Optional

from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TRCK,
    TPOS,
)
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

from musicgrab.models.track import Track
from musicgrab.utils import print_error, print_success, print_warning


class MetadataEmbedder:
    """Embeds metadata into audio files using mutagen."""

    def __init__(self, config) -> None:
        self.config = config

    def embed(self, track: Track, file_path: Path) -> bool:
        """Embed metadata into an audio file.

        Args:
            track: The Track object with metadata.
            file_path: Path to the audio file.

        Returns:
            True if successful, False otherwise.
        """
        if not file_path.exists():
            print_error(f"File not found: {file_path}")
            return False

        ext = file_path.suffix.lower().lstrip(".")

        try:
            if ext == "mp3":
                return self._embed_mp3(track, file_path)
            elif ext == "flac":
                return self._embed_flac(track, file_path)
            elif ext == "m4a":
                return self._embed_mp4(track, file_path)
            elif ext in ("ogg", "opus"):
                return self._embed_ogg(track, file_path)
            elif ext == "wav":
                # WAV doesn't support metadata embedding well
                print_warning("WAV files have limited metadata support")
                return self._embed_id3_wav(track, file_path)
            else:
                print_warning(f"Unsupported format for metadata: {ext}")
                return False
        except Exception as e:
            print_error(f"Failed to embed metadata: {e}")
            return False

    def _embed_mp3(self, track: Track, file_path: Path) -> bool:
        """Embed metadata into an MP3 file using ID3 tags."""
        audio_file = MP3(file_path, ID3=ID3)

        # Create ID3 tags if they don't exist
        try:
            audio_file.add_tags()
        except Exception:
            pass  # Tags already exist

        # Title
        if track.title:
            audio_file.tags.add(TIT2(encoding=3, text=track.title))

        # Artist
        if track.artist:
            audio_file.tags.add(TPE1(encoding=3, text=track.artist))
            audio_file.tags.add(TPE2(encoding=3, text=track.artist))

        # Album
        if track.album:
            audio_file.tags.add(TALB(encoding=3, text=track.album))

        # Track number
        if track.track_number:
            audio_file.tags.add(TRCK(encoding=3, text=str(track.track_number)))

        # Disc number
        if track.disc_number:
            audio_file.tags.add(TPOS(encoding=3, text=str(track.disc_number)))

        # Year
        if track.year:
            audio_file.tags.add(TDRC(encoding=3, text=str(track.year)))

        # Genre
        if track.genre:
            audio_file.tags.add(TCON(encoding=3, text=track.genre))

        # Artwork
        if self.config.embed_artwork and track.thumbnail_data:
            audio_file.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # Cover (front)
                    desc="Cover",
                    data=track.thumbnail_data,
                )
            )

        audio_file.save()
        return True

    def _embed_flac(self, track: Track, file_path: Path) -> bool:
        """Embed metadata into a FLAC file."""
        audio_file = FLAC(file_path)

        if track.title:
            audio_file["title"] = track.title
        if track.artist:
            audio_file["artist"] = track.artist
        if track.album:
            audio_file["album"] = track.album
        if track.track_number:
            audio_file["tracknumber"] = str(track.track_number)
        if track.disc_number:
            audio_file["discnumber"] = str(track.disc_number)
        if track.year:
            audio_file["date"] = str(track.year)
        if track.genre:
            audio_file["genre"] = track.genre

        # Artwork
        if self.config.embed_artwork and track.thumbnail_data:
            from mutagen.flac import Picture

            pic = Picture()
            pic.data = track.thumbnail_data
            pic.type = 3  # Cover (front)
            pic.mime = "image/jpeg"
            pic.width = 0
            pic.height = 0
            pic.depth = 0
            pic.length = 0
            audio_file.clear_pictures()
            audio_file.add_picture(pic)

        audio_file.save()
        return True

    def _embed_mp4(self, track: Track, file_path: Path) -> bool:
        """Embed metadata into an M4A file."""
        audio_file = MP4(file_path)

        if track.title:
            audio_file["\xa9nam"] = track.title
        if track.artist:
            audio_file["\xa9ART"] = track.artist
        if track.album:
            audio_file["\xa9alb"] = track.album
        if track.track_number:
            audio_file["trkn"] = [(int(track.track_number), 0)]
        if track.year:
            audio_file["\xa9day"] = str(track.year)
        if track.genre:
            audio_file["\xa9gen"] = track.genre

        # Artwork
        if self.config.embed_artwork and track.thumbnail_data:
            from mutagen.mp4 import MP4Cover

            audio_file["covr"] = [
                MP4Cover(track.thumbnail_data, imageformat=MP4Cover.FORMAT_JPEG)
            ]

        audio_file.save()
        return True

    def _embed_ogg(self, track: Track, file_path: Path) -> bool:
        """Embed metadata into an OGG/Opus file."""
        audio_file = OggVorbis(file_path)

        if track.title:
            audio_file["title"] = track.title
        if track.artist:
            audio_file["artist"] = track.artist
        if track.album:
            audio_file["album"] = track.album
        if track.track_number:
            audio_file["tracknumber"] = str(track.track_number)
        if track.year:
            audio_file["date"] = str(track.year)
        if track.genre:
            audio_file["genre"] = track.genre

        audio_file.save()
        return True

    def _embed_id3_wav(self, track: Track, file_path: Path) -> bool:
        """Embed ID3 tags into a WAV file (limited support)."""
        try:
            audio_file = MP3(file_path, ID3=ID3)
            try:
                audio_file.add_tags()
            except Exception:
                pass

            if track.title:
                audio_file.tags.add(TIT2(encoding=3, text=track.title))
            if track.artist:
                audio_file.tags.add(TPE1(encoding=3, text=track.artist))
            if track.album:
                audio_file.tags.add(TALB(encoding=3, text=track.album))
            if track.track_number:
                audio_file.tags.add(TRCK(encoding=3, text=str(track.track_number)))
            if track.year:
                audio_file.tags.add(TDRC(encoding=3, text=str(track.year)))
            if track.genre:
                audio_file.tags.add(TCON(encoding=3, text=track.genre))

            audio_file.save()
            return True
        except Exception as e:
            print_warning(f"Could not embed metadata in WAV: {e}")
            return False

    def embed_artwork(self, track: Track, file_path: Path) -> bool:
        """Embed only artwork into an audio file."""
        if not track.thumbnail_data:
            return False

        ext = file_path.suffix.lower().lstrip(".")

        try:
            if ext == "mp3":
                audio_file = MP3(file_path, ID3=ID3)
                try:
                    audio_file.add_tags()
                except Exception:
                    pass
                audio_file.tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=track.thumbnail_data,
                    )
                )
                audio_file.save()
                return True
            elif ext == "m4a":
                audio_file = MP4(file_path)
                from mutagen.mp4 import MP4Cover

                audio_file["covr"] = [
                    MP4Cover(track.thumbnail_data, imageformat=MP4Cover.FORMAT_JPEG)
                ]
                audio_file.save()
                return True
            elif ext == "flac":
                audio_file = FLAC(file_path)
                from mutagen.flac import Picture

                pic = Picture()
                pic.data = track.thumbnail_data
                pic.type = 3
                pic.mime = "image/jpeg"
                audio_file.clear_pictures()
                audio_file.add_picture(pic)
                audio_file.save()
                return True
            else:
                print_warning(f"Artwork embedding not supported for: {ext}")
                return False
        except Exception as e:
            print_error(f"Failed to embed artwork: {e}")
            return False
