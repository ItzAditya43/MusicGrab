"""YouTube source module for MusicGrab.

Handles downloading audio from YouTube videos and playlists using yt-dlp.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional

# Generous but bounded — a stalled yt-dlp process (network hiccup, retry
# loop, rate-limit backoff) would otherwise block its calling thread
# forever with no recovery, which is fatal for an unattended multi-track
# playlist job: one bad track hangs the entire batch permanently instead
# of just failing that one track and moving on.
_METADATA_TIMEOUT = 60
_DOWNLOAD_TIMEOUT = 600

from musicgrab.models.playlist import Playlist
from musicgrab.models.track import Track
from musicgrab.utils import (
    console,
    extract_youtube_video_id,
    is_youtube_url,
    print_error,
    print_info,
    print_success,
    print_warning,
    sanitize_path_component,
)


def _subprocess_env() -> dict:
    """Environment for spawning external tools like yt-dlp.

    PyInstaller points LD_LIBRARY_PATH at its own bundled libs (and stashes
    the real value in LD_LIBRARY_PATH_ORIG) so the frozen app's own Python
    can find them. That override leaks into any child process we spawn, so
    a system-installed yt-dlp/ffmpeg ends up loading PyInstaller's bundled
    libcrypto/libssl instead of the system ones and crashes with something
    like "OPENSSL_3.3.0 not found". Restore the original value for children.
    """
    env = os.environ.copy()
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


class YouTubeSource:
    """Handles YouTube video and playlist downloads."""

    def __init__(self, config) -> None:
        self.config = config

    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid YouTube URL."""
        return is_youtube_url(url)

    def get_info(self, url: str) -> dict:
        """Get metadata for a YouTube video or playlist using yt-dlp."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-warnings",
            url,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=_subprocess_env(), timeout=_METADATA_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            print_error(f"Timed out fetching info for: {url}")
            return {}
        if result.returncode != 0:
            print_error(f"Failed to fetch info: {result.stderr.strip()}")
            return {}

        # For playlists, yt-dlp outputs multiple JSON objects (one per line)
        lines = result.stdout.strip().split("\n")
        if len(lines) == 1:
            return json.loads(lines[0])
        else:
            # It's a playlist
            entries = []
            for line in lines:
                if line.strip():
                    entries.append(json.loads(line))
            return {"_type": "playlist", "entries": entries}

    def parse_video(self, url: str) -> Track:
        """Parse a single YouTube video into a Track."""
        info = self.get_info(url)
        if not info:
            return Track(title="Unknown", artist="Unknown", source="youtube", source_url=url)

        title = info.get("title", "Unknown")
        artist = info.get("artist") or info.get("uploader", "Unknown")
        duration = info.get("duration", 0)
        thumbnail = info.get("thumbnail", "")
        video_id = info.get("id", "")

        # Try to extract artist and title from the video title
        # Common format: "Artist - Title"
        if " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()

        track = Track(
            title=title,
            artist=artist,
            album=info.get("album", ""),
            duration=duration,
            source="youtube",
            source_url=url,
            source_id=video_id,
            thumbnail_url=thumbnail,
        )
        return track

    def parse_playlist(self, url: str) -> Playlist:
        """Parse a YouTube playlist into a Playlist object."""
        info = self.get_info(url)
        if not info:
            return Playlist(title="Unknown Playlist", source="youtube", source_url=url)

        if info.get("_type") == "playlist" or "entries" in info:
            entries = info.get("entries", [])
            playlist_title = info.get("title", "Unknown Playlist")
            playlist = Playlist(
                title=playlist_title,
                source="youtube",
                source_url=url,
                source_id=info.get("id", ""),
                description=info.get("description", ""),
                thumbnail_url=info.get("thumbnail", ""),
                owner=info.get("uploader", ""),
                total_tracks=len(entries),
            )

            for entry in entries:
                if not entry:
                    continue
                title = entry.get("title", "Unknown")
                artist = entry.get("artist") or entry.get("uploader", "Unknown")
                duration = entry.get("duration", 0)
                thumbnail = entry.get("thumbnail", "")
                video_id = entry.get("id", "")

                # Try to extract artist and title from the video title
                if " - " in title:
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()

                track = Track(
                    title=title,
                    artist=artist,
                    duration=duration,
                    source="youtube",
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    source_id=video_id,
                    thumbnail_url=thumbnail,
                )
                playlist.add_track(track)

            return playlist
        else:
            # Single video treated as a playlist with one track
            track = self.parse_video(url)
            playlist = Playlist(
                title=track.title,
                source="youtube",
                source_url=url,
                source_id=info.get("id", ""),
                total_tracks=1,
            )
            playlist.add_track(track)
            return playlist

    def download_track(
        self,
        track: Track,
        output_dir: Path,
        progress_callback=None,
    ) -> Optional[Path]:
        """Download a single YouTube track as audio."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use video ID as the output template for reliability
        video_id = track.source_id or extract_youtube_video_id(track.source_url) or "unknown"
        ext = self.config.audio_format
        output_template = str(output_dir / f"{video_id}.%(ext)s")

        # Build yt-dlp command
        cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", ext,
            "--audio-quality", self.config.audio_quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--no-warnings",
            "--newline",
            "-o", output_template,
            track.source_url,
        ]

        if self.config.overwrite:
            cmd.append("--force-overwrite")

        # A single non-zero exit used to be treated as a permanent failure.
        # In practice most failures on a long playlist run are transient
        # (momentary YouTube throttling, network hiccup) and a retry
        # succeeds — so give it a couple of extra tries (not on a genuine
        # timeout though; that already waited the full budget once).
        returncode = None
        timed_out = False
        for attempt in range(3):
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=_subprocess_env(),
            )

            timed_out = False

            def _kill_on_timeout():
                nonlocal timed_out
                timed_out = True
                process.kill()

            watchdog = threading.Timer(_DOWNLOAD_TIMEOUT, _kill_on_timeout)
            watchdog.start()
            try:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        if progress_callback:
                            progress_callback(line)
                        # Parse progress from yt-dlp output
                        if "%" in line:
                            console.print(f"  {line}")

                process.wait()
            finally:
                watchdog.cancel()

            returncode = process.returncode
            if timed_out or returncode == 0:
                break
            if attempt < 2:
                time.sleep(2 * (attempt + 1))

        if timed_out:
            print_error(f"Timed out downloading: {track.display_title}")
            return None

        # Even if yt-dlp returns non-zero, the file may have been downloaded
        # (e.g., due to warnings). Check for the file first.
        if returncode != 0:
            # Check if file was still downloaded despite the error
            expected_file = output_dir / f"{video_id}.{ext}"
            if not expected_file.exists():
                # Try to find any matching file by video ID
                found = False
                for f in output_dir.glob(f"{video_id}.*"):
                    if f.suffix.lstrip(".") in ("mp3", "m4a", "flac", "wav", "ogg", "opus"):
                        found = True
                        break
                if not found:
                    print_error(f"Failed to download: {track.display_title}")
                    return None

        # Find the downloaded file by video ID
        expected_file = output_dir / f"{video_id}.{ext}"
        if expected_file.exists():
            # Rename to desired filename
            desired_name = track.filename
            desired_file = output_dir / f"{desired_name}.{ext}"
            if desired_file != expected_file:
                if desired_file.exists() and not self.config.overwrite:
                    print_warning(f"File already exists: {desired_file.name}")
                    track.output_path = desired_file
                    track.downloaded = True
                    track.file_size = desired_file.stat().st_size
                    return desired_file
                expected_file.rename(desired_file)
            track.output_path = desired_file
            track.downloaded = True
            track.file_size = desired_file.stat().st_size
            return desired_file

        # Try to find any matching file by video ID
        for f in output_dir.glob(f"{video_id}.*"):
            if f.suffix.lstrip(".") in ("mp3", "m4a", "flac", "wav", "ogg", "opus"):
                # Rename to desired filename
                desired_name = track.filename
                desired_file = output_dir / f"{desired_name}{f.suffix}"
                if desired_file != f:
                    if desired_file.exists() and not self.config.overwrite:
                        track.output_path = desired_file
                        track.downloaded = True
                        track.file_size = desired_file.stat().st_size
                        return desired_file
                    f.rename(desired_file)
                track.output_path = desired_file
                track.downloaded = True
                track.file_size = desired_file.stat().st_size
                return desired_file

        print_error(f"Downloaded file not found for: {track.display_title}")
        return None

    def download_playlist(
        self,
        playlist: Playlist,
        output_dir: Path,
        progress_callback=None,
    ) -> List[Path]:
        """Download all tracks in a YouTube playlist."""
        downloaded_files = []
        total = playlist.track_count

        for i, track in enumerate(playlist.tracks, 1):
            if progress_callback:
                progress_callback(f"Downloading track {i}/{total}: {track.display_title}")

            # Create subdirectory for playlist
            playlist_dir = output_dir / sanitize_path_component(playlist.title)
            file_path = self.download_track(track, playlist_dir, progress_callback)

            if file_path:
                downloaded_files.append(file_path)
                print_success(f"Downloaded: {track.display_title}")
            else:
                print_error(f"Failed: {track.display_title}")

        return downloaded_files

    def search(self, query: str, max_results: int = 5) -> List[Track]:
        """Search for tracks on YouTube."""
        # A tab-delimited --print template sidesteps two footguns of the
        # legacy --get-id/--get-title/--get-duration flags: their output
        # order doesn't actually match the flag order (title comes before
        # id), and --get-duration prints a formatted "M:SS" string rather
        # than a plain number.
        cmd = [
            "yt-dlp",
            "--print", "%(id)s\t%(title)s\t%(duration)s",
            "--no-warnings",
            # ytsearch: (no count) only ever fetches a single result no
            # matter what --playlist-items says — the count has to be
            # baked into the search spec itself (ytsearchN:).
            f"ytsearch{max_results}:{query}",
        ]
        # A failed search used to be reported back as "Not found" —
        # indistinguishable from a track that genuinely doesn't exist on
        # YouTube. In practice, on a long playlist run, most failures here
        # are transient (network hiccup, momentary YouTube throttling) and
        # a single retry succeeds. Retry a couple of times with backoff
        # before giving up, and log the real reason on final failure so
        # "not found" in the UI isn't a red herring for a network blip.
        result = None
        last_stderr = ""
        for attempt in range(3):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, env=_subprocess_env(), timeout=_METADATA_TIMEOUT
                )
            except subprocess.TimeoutExpired:
                last_stderr = "timed out"
                result = None
            else:
                if result.returncode == 0:
                    break
                last_stderr = (result.stderr or "").strip().splitlines()[-1] if result.stderr else ""
                result = None
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        if result is None:
            print_error(f"Search failed for: {query} ({last_stderr or 'unknown error'})")
            return []

        tracks = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            video_id, title, duration_raw = parts
            try:
                duration = int(float(duration_raw))
            except ValueError:
                duration = 0
            track = Track(
                title=title,
                artist="YouTube",
                duration=duration,
                source="youtube",
                source_url=f"https://www.youtube.com/watch?v={video_id}",
                source_id=video_id,
            )
            tracks.append(track)

        return tracks
