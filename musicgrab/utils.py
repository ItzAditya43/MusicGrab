"""Utility functions for MusicGrab."""

import os
import re
import shutil
import string
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

# Global console instance
console = Console()


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Remove leading/trailing dots and spaces
    name = name.strip(". ")
    # Truncate if too long
    if len(name) > max_length:
        name = name[:max_length]
    return name or "unnamed"


def sanitize_path_component(name: str) -> str:
    """Sanitize a string for use as a path component (directory name)."""
    name = sanitize_filename(name, max_length=100)
    return name


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 0:
        return "0:00"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = int(minutes // 60)
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: float) -> str:
    """Format bytes into a human-readable file size string."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def get_audio_extension(fmt: str) -> str:
    """Get the file extension for an audio format."""
    fmt = fmt.lower().strip()
    if fmt in ("mp3", "m4a", "flac", "wav", "ogg", "opus", "wma"):
        return fmt
    return "mp3"


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube URL."""
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=",
        r"(?:https?://)?(?:www\.)?youtu\.be/",
        r"(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/",
    ]
    return any(re.match(p, url) for p in patterns)


def is_spotify_url(url: str) -> bool:
    """Check if a URL is a Spotify URL."""
    patterns = [
        r"(?:https?://)?open\.spotify\.com/track/",
        r"(?:https?://)?open\.spotify\.com/album/",
        r"(?:https?://)?open\.spotify\.com/artist/",
        r"(?:https?://)?open\.spotify\.com/playlist/",
        r"(?:https?://)?open\.spotify\.com/show/",
    ]
    return any(re.match(p, url) for p in patterns)


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract the video ID from a YouTube URL."""
    patterns = [
        r"(?:v=|\/)([a-zA-Z0-9_-]{11}).*",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_spotify_id(url: str) -> Optional[tuple[str, str]]:
    """Extract the type and ID from a Spotify URL.

    Returns a tuple of (type, id) or None.
    """
    match = re.search(
        r"open\.spotify\.com/(track|album|artist|playlist|show)/([a-zA-Z0-9]+)",
        url,
    )
    if match:
        return match.group(1), match.group(2)
    return None


def print_banner() -> None:
    """Print the MusicGrab banner."""
    banner = """
    ╔══════════════════════════════════════╗
    ║          MusicGrab v1.0.0            ║
    ║   A CLI music downloader & library   ║
    ╚══════════════════════════════════════╝
    """
    console.print(Panel(banner, style="cyan", expand=False))


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"✓ [green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"✗ [red]{message}[/red]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"ℹ [blue]{message}[/blue]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"⚠ [yellow]{message}[/yellow]")


def create_progress() -> Progress:
    """Create a rich Progress instance for downloads."""
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def create_table(title: str, columns: list[str]) -> Table:
    """Create a rich Table with the given title and columns."""
    table = Table(title=title, show_lines=True)
    for col in columns:
        table.add_column(col, style="cyan")
    return table


def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed."""
    return shutil.which("ffmpeg") is not None


def check_yt_dlp() -> bool:
    """Check if yt-dlp is installed."""
    return shutil.which("yt-dlp") is not None


def ensure_ffmpeg() -> bool:
    """Ensure ffmpeg is available, print error if not."""
    if not check_ffmpeg():
        print_error("ffmpeg is not installed. Please install it first.")
        print_info("On Ubuntu/Debian: sudo apt install ffmpeg")
        print_info("On macOS: brew install ffmpeg")
        print_info("On Windows: https://ffmpeg.org/download.html")
        return False
    return True


def ensure_yt_dlp() -> bool:
    """Ensure yt-dlp is available, print error if not."""
    if not check_yt_dlp():
        print_error("yt-dlp is not installed. Please install it first.")
        print_info("pip install yt-dlp")
        return False
    return True
