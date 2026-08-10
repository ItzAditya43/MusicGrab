"""Artwork saving module for MusicGrab.

Downloads and saves album artwork/thumbnails from URLs.
"""

import io
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from musicgrab.models.track import Track
from musicgrab.utils import (
    console,
    format_file_size,
    print_error,
    print_info,
    print_success,
    print_warning,
    sanitize_filename,
)


class ArtworkSaver:
    """Downloads and saves album artwork."""

    def __init__(self, config) -> None:
        self.config = config

    def download_artwork(self, url: str, max_size: int = 1024) -> Optional[bytes]:
        """Download artwork from a URL and return as bytes.

        Args:
            url: The URL of the artwork image.
            max_size: Maximum dimension in pixels.

        Returns:
            Image data as bytes, or None if failed.
        """
        if not url:
            return None

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            image_data = response.content

            # Resize if needed
            if max_size > 0:
                img = Image.open(io.BytesIO(image_data))
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    output = io.BytesIO()
                    img.save(output, format="JPEG", quality=90)
                    image_data = output.getvalue()

            return image_data
        except Exception as e:
            print_warning(f"Failed to download artwork: {e}")
            return None

    def save_artwork(
        self,
        track: Track,
        output_dir: Path,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """Save artwork for a track to a file.

        Args:
            track: The Track object with thumbnail_url.
            output_dir: Directory to save the artwork.
            filename: Optional filename (without extension).

        Returns:
            Path to the saved artwork file, or None if failed.
        """
        if not track.thumbnail_url:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = track.filename

        filename = sanitize_filename(filename)
        output_path = output_dir / f"{filename}.jpg"

        image_data = self.download_artwork(track.thumbnail_url)
        if image_data:
            with open(output_path, "wb") as f:
                f.write(image_data)
            print_success(f"Artwork saved: {output_path}")
            return output_path
        else:
            print_warning(f"Could not save artwork for: {track.display_title}")
            return None

    def save_artwork_for_album(
        self,
        album_title: str,
        artist: str,
        thumbnail_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Save album artwork.

        Args:
            album_title: The album title.
            artist: The artist name.
            thumbnail_url: URL of the artwork.
            output_dir: Directory to save the artwork.

        Returns:
            Path to the saved artwork file, or None if failed.
        """
        if not thumbnail_url:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        filename = sanitize_filename(f"{artist} - {album_title}")
        output_path = output_dir / f"{filename}.jpg"

        image_data = self.download_artwork(thumbnail_url)
        if image_data:
            with open(output_path, "wb") as f:
                f.write(image_data)
            print_success(f"Album artwork saved: {output_path}")
            return output_path
        else:
            print_warning(f"Could not save album artwork for: {album_title}")
            return None

    def load_artwork_into_track(self, track: Track) -> bool:
        """Load artwork data into a track object from its thumbnail URL.

        Args:
            track: The Track object to populate.

        Returns:
            True if artwork was loaded, False otherwise.
        """
        if not track.thumbnail_url:
            return False

        image_data = self.download_artwork(track.thumbnail_url)
        if image_data:
            track.thumbnail_data = image_data
            return True
        return False
