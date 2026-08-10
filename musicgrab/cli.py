"""Main CLI entry point for MusicGrab.

Usage:
    musicgrab <URL>
    musicgrab search <query>
    musicgrab library [scan|list|stats|organize|search]
    musicgrab config [set|show|spotify]
    musicgrab queue [list|save|load|clear]
"""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from musicgrab import __version__
from musicgrab.artwork.saver import ArtworkSaver
from musicgrab.config import config, get_config
from musicgrab.library.manager import LibraryManager
from musicgrab.metadata.embedder import MetadataEmbedder
from musicgrab.models.album import Album
from musicgrab.models.playlist import Playlist
from musicgrab.models.track import Track
from musicgrab.queue.download_queue import DownloadQueue
from musicgrab.sources.spotify import SpotifySource
from musicgrab.sources.youtube import YouTubeSource
from musicgrab.utils import (
    console,
    ensure_ffmpeg,
    ensure_yt_dlp,
    format_duration,
    format_file_size,
    is_spotify_url,
    is_youtube_url,
    print_banner,
    print_error,
    print_info,
    print_success,
    print_warning,
    sanitize_path_component,
)

# Initialize modules
youtube_source = YouTubeSource(config)
spotify_source = SpotifySource(config)
metadata_embedder = MetadataEmbedder(config)
artwork_saver = ArtworkSaver(config)
library_manager = LibraryManager(config)
download_queue = DownloadQueue(config)


def detect_source(url: str) -> str:
    """Detect the source type from a URL."""
    if is_youtube_url(url):
        return "youtube"
    elif is_spotify_url(url):
        return "spotify"
    return "unknown"


def detect_content_type(url: str) -> str:
    """Detect the content type from a URL."""
    if "playlist" in url or "list=" in url:
        return "playlist"
    elif "album" in url:
        return "album"
    elif "artist" in url:
        return "artist"
    elif "track" in url or "watch?v=" in url or "youtu.be/" in url:
        return "track"
    elif "shorts" in url:
        return "track"
    return "unknown"


def print_download_header(source: str, content_type: str, track_count: int) -> None:
    """Print the download header panel."""
    console.print()
    console.print(Panel(
        f"[cyan]MusicGrab[/cyan] [dim]v{__version__}[/dim]\n"
        f"──────────────────────────────\n"
        f"Source:  {source.capitalize()}\n"
        f"Type:    {content_type.capitalize()}\n"
        f"Tracks:  {track_count}",
        title="MusicGrab",
        border_style="cyan",
        expand=False,
    ))
    console.print()


def download_youtube_url(url: str, output_dir: Path) -> list:
    """Download from a YouTube URL."""
    if not ensure_yt_dlp() or not ensure_ffmpeg():
        return []

    content_type = detect_content_type(url)

    if content_type == "playlist":
        playlist = youtube_source.parse_playlist(url)
        print_download_header("YouTube", "Playlist", playlist.track_count)

        # Load artwork for all tracks
        for track in playlist.tracks:
            if track.thumbnail_url:
                artwork_saver.load_artwork_into_track(track)

        # Download all tracks
        files = youtube_source.download_playlist(playlist, output_dir)

        # Embed metadata for downloaded tracks
        for track in playlist.tracks:
            if track.output_path and config.embed_metadata:
                metadata_embedder.embed(track, track.output_path)

        # Save artwork
        if config.save_artwork:
            artwork_dir = output_dir / "artwork"
            for track in playlist.tracks:
                if track.thumbnail_url:
                    artwork_saver.save_artwork(track, artwork_dir)

        return files

    else:
        # Single video
        track = youtube_source.parse_video(url)
        print_download_header("YouTube", "Track", 1)

        # Load artwork
        if track.thumbnail_url:
            artwork_saver.load_artwork_into_track(track)

        # Download
        file_path = youtube_source.download_track(track, output_dir)

        # Embed metadata
        if file_path and config.embed_metadata:
            metadata_embedder.embed(track, file_path)

        # Save artwork
        if file_path and config.save_artwork:
            artwork_dir = output_dir / "artwork"
            artwork_saver.save_artwork(track, artwork_dir)

        return [file_path] if file_path else []


def download_spotify_url(url: str, output_dir: Path) -> list:
    """Download from a Spotify URL (metadata + search-based download)."""
    content_type = detect_content_type(url)

    if content_type == "playlist":
        playlist = spotify_source.parse_playlist(url)
        print_download_header("Spotify", "Playlist", playlist.track_count)

        # Export metadata
        metadata_file = output_dir / f"{playlist.title}_metadata.json"
        spotify_source.export_metadata(playlist, metadata_file)

        # Export CSV
        csv_file = output_dir / f"{playlist.title}_tracks.csv"
        spotify_source.export_to_csv(playlist, csv_file)

        # Load artwork for all tracks
        for track in playlist.tracks:
            if track.thumbnail_url:
                artwork_saver.load_artwork_into_track(track)

        # Save artwork
        if config.save_artwork:
            artwork_dir = output_dir / "artwork"
            for track in playlist.tracks:
                if track.thumbnail_url:
                    artwork_saver.save_artwork(track, artwork_dir)

        # For Spotify, we can optionally search YouTube for audio
        # This requires yt-dlp
        if ensure_yt_dlp() and ensure_ffmpeg():
            print_info("Searching YouTube for audio tracks...")
            downloaded_files = []
            for i, track in enumerate(playlist.tracks, 1):
                search_query = f"{track.artist} {track.title}"
                results = youtube_source.search(search_query, max_results=1)
                if results:
                    yt_track = results[0]
                    # Copy metadata from Spotify track
                    yt_track.title = track.title
                    yt_track.artist = track.artist
                    yt_track.album = track.album
                    yt_track.duration = track.duration
                    yt_track.track_number = track.track_number
                    yt_track.disc_number = track.disc_number
                    yt_track.year = track.year
                    yt_track.genre = track.genre
                    yt_track.thumbnail_url = track.thumbnail_url
                    yt_track.thumbnail_data = track.thumbnail_data

                    playlist_dir = output_dir / sanitize_path_component(playlist.title)
                    file_path = youtube_source.download_track(yt_track, playlist_dir)

                    if file_path and config.embed_metadata:
                        metadata_embedder.embed(yt_track, file_path)

                    if file_path:
                        downloaded_files.append(file_path)
                        print_success(f"Downloaded: {track.display_title}")
                    else:
                        print_error(f"Failed: {track.display_title}")
                else:
                    print_warning(f"Could not find on YouTube: {track.display_title}")

            return downloaded_files
        else:
            print_info("yt-dlp/ffmpeg not available. Metadata exported only.")
            return []

    elif content_type == "album":
        album = spotify_source.parse_album(url)
        print_download_header("Spotify", "Album", album.track_count)

        # Export metadata
        metadata_file = output_dir / f"{album.artist} - {album.title}_metadata.json"
        spotify_source.export_metadata(
            Playlist(
                title=album.title,
                source=album.source,
                source_url=album.source_url,
                source_id=album.source_id,
                tracks=album.tracks,
                thumbnail_url=album.thumbnail_url,
                owner=album.artist,
            ),
            metadata_file,
        )

        # Load artwork
        for track in album.tracks:
            if track.thumbnail_url:
                artwork_saver.load_artwork_into_track(track)

        # Save artwork
        if config.save_artwork:
            artwork_dir = output_dir / "artwork"
            artwork_saver.save_artwork_for_album(
                album.title, album.artist, album.thumbnail_url, artwork_dir
            )

        # Download via YouTube search
        if ensure_yt_dlp() and ensure_ffmpeg():
            print_info("Searching YouTube for audio tracks...")
            downloaded_files = []
            album_dir = output_dir / sanitize_path_component(f"{album.artist} - {album.title}")
            for track in album.tracks:
                search_query = f"{track.artist} {track.title}"
                results = youtube_source.search(search_query, max_results=1)
                if results:
                    yt_track = results[0]
                    yt_track.title = track.title
                    yt_track.artist = track.artist
                    yt_track.album = track.album
                    yt_track.duration = track.duration
                    yt_track.track_number = track.track_number
                    yt_track.disc_number = track.disc_number
                    yt_track.year = track.year
                    yt_track.genre = track.genre
                    yt_track.thumbnail_url = track.thumbnail_url
                    yt_track.thumbnail_data = track.thumbnail_data

                    file_path = youtube_source.download_track(yt_track, album_dir)

                    if file_path and config.embed_metadata:
                        metadata_embedder.embed(yt_track, file_path)

                    if file_path:
                        downloaded_files.append(file_path)
                        print_success(f"Downloaded: {track.display_title}")
                    else:
                        print_error(f"Failed: {track.display_title}")
                else:
                    print_warning(f"Could not find on YouTube: {track.display_title}")

            return downloaded_files
        else:
            print_info("yt-dlp/ffmpeg not available. Metadata exported only.")
            return []

    else:
        # Single track
        track = spotify_source.parse_track(url)
        print_download_header("Spotify", "Track", 1)

        # Export metadata
        metadata_file = output_dir / f"{track.artist} - {track.title}_metadata.json"
        spotify_source.export_metadata(
            Playlist(
                title=track.title,
                source=track.source,
                source_url=track.source_url,
                source_id=track.source_id,
                tracks=[track],
                thumbnail_url=track.thumbnail_url,
            ),
            metadata_file,
        )

        # Load artwork
        if track.thumbnail_url:
            artwork_saver.load_artwork_into_track(track)

        # Save artwork
        if config.save_artwork:
            artwork_dir = output_dir / "artwork"
            artwork_saver.save_artwork(track, artwork_dir)

        # Download via YouTube search
        if ensure_yt_dlp() and ensure_ffmpeg():
            search_query = f"{track.artist} {track.title}"
            results = youtube_source.search(search_query, max_results=1)
            if results:
                yt_track = results[0]
                yt_track.title = track.title
                yt_track.artist = track.artist
                yt_track.album = track.album
                yt_track.duration = track.duration
                yt_track.track_number = track.track_number
                yt_track.disc_number = track.disc_number
                yt_track.year = track.year
                yt_track.genre = track.genre
                yt_track.thumbnail_url = track.thumbnail_url
                yt_track.thumbnail_data = track.thumbnail_data

                file_path = youtube_source.download_track(yt_track, output_dir)

                if file_path and config.embed_metadata:
                    metadata_embedder.embed(yt_track, file_path)

                return [file_path] if file_path else []
            else:
                print_warning(f"Could not find on YouTube: {track.display_title}")
                return []
        else:
            print_info("yt-dlp/ffmpeg not available. Metadata exported only.")
            return []


def print_download_summary(files: list, output_dir: Path) -> None:
    """Print the download summary."""
    console.print()
    if files:
        console.print(Panel(
            "[green]Download complete![/green]\n"
            f"──────────────────────────────\n"
            f"✓ {len(files)} file(s) downloaded\n"
            f"✓ Metadata embedded\n"
            f"✓ Artwork saved\n"
            f"\n"
            f"Saved to: {output_dir}",
            title="MusicGrab",
            border_style="green",
            expand=False,
        ))
    else:
        console.print(Panel(
            "[red]No files were downloaded.[/red]\n"
            f"──────────────────────────────\n"
            f"Check the errors above for details.",
            title="MusicGrab",
            border_style="red",
            expand=False,
        ))


# ===== CLI Commands =====

class MusicGrabGroup(click.Group):
    """Custom Click group that allows passing a URL directly as the first argument."""

    def parse_args(self, ctx: click.Context, args: list) -> list:
        """Parse arguments, treating the first arg as a URL if it's not a subcommand."""
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            # First arg is a URL, not a subcommand
            ctx.meta["_direct_url"] = args[0]
            args = args[1:]
        return super().parse_args(ctx, args)


@click.group(cls=MusicGrabGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="MusicGrab")
@click.option("--output", "-o", "output_dir", type=click.Path(), default=None,
              help="Output directory for downloads")
@click.option("--format", "-f", "audio_format", type=click.Choice(["mp3", "m4a", "flac", "wav", "ogg"]),
              default=None, help="Audio format")
@click.option("--quality", "-q", "audio_quality", type=click.Choice(["128", "192", "256", "320"]),
              default=None, help="Audio quality (kbps)")
@click.option("--no-metadata", is_flag=True, default=False, help="Skip metadata embedding")
@click.option("--no-artwork", is_flag=True, default=False, help="Skip artwork saving")
@click.option("--overwrite", is_flag=True, default=False, help="Overwrite existing files")
@click.pass_context
def main(
    ctx: click.Context,
    output_dir: Optional[str],
    audio_format: Optional[str],
    audio_quality: Optional[str],
    no_metadata: bool,
    no_artwork: bool,
    overwrite: bool,
) -> None:
    """MusicGrab — A CLI music downloader and library tool.

    Download music from YouTube and Spotify directly from the command line.

    Usage:
        musicgrab <URL>           Download from a URL
        musicgrab search <query>  Search for tracks
        musicgrab library         Manage local library
        musicgrab config          Configure settings
        musicgrab queue           Manage download queue
    """
    # Apply CLI options to config
    if output_dir:
        config.download_dir = Path(output_dir)
    if audio_format:
        config.audio_format = audio_format
    if audio_quality:
        config.audio_quality = audio_quality
    if no_metadata:
        config.embed_metadata = False
    if no_artwork:
        config.embed_artwork = False
        config.save_artwork = False
    if overwrite:
        config.overwrite = True

    config.ensure_dirs()

    # If no subcommand and a direct URL was passed, download it
    if ctx.invoked_subcommand is None:
        direct_url = ctx.meta.get("_direct_url")
        if direct_url:
            _do_download(direct_url)
        else:
            click.echo(ctx.get_help())
            ctx.exit()


def _do_download(url: str) -> None:
    """Internal function to handle downloading from a URL."""
    source = detect_source(url)
    if source == "unknown":
        print_error(f"Could not detect source from URL: {url}")
        print_info("Supported sources: YouTube, Spotify")
        sys.exit(1)

    output_path = config.download_dir

    if source == "youtube":
        files = download_youtube_url(url, output_path)
    elif source == "spotify":
        files = download_spotify_url(url, output_path)
    else:
        print_error(f"Unsupported source: {source}")
        sys.exit(1)

    print_download_summary(files, output_path)


@main.command()
@click.argument("url")
@click.option("--output", "-o", "output_dir", type=click.Path(), default=None,
              help="Output directory")
@click.option("--format", "-f", "audio_format", type=click.Choice(["mp3", "m4a", "flac", "wav", "ogg"]),
              default=None, help="Audio format")
@click.option("--quality", "-q", "audio_quality", type=click.Choice(["128", "192", "256", "320"]),
              default=None, help="Audio quality (kbps)")
@click.option("--no-metadata", is_flag=True, default=False, help="Skip metadata embedding")
@click.option("--no-artwork", is_flag=True, default=False, help="Skip artwork saving")
@click.option("--overwrite", is_flag=True, default=False, help="Overwrite existing files")
def download(
    url: str,
    output_dir: Optional[str],
    audio_format: Optional[str],
    audio_quality: Optional[str],
    no_metadata: bool,
    no_artwork: bool,
    overwrite: bool,
) -> None:
    """Download music from a YouTube or Spotify URL."""
    # Apply options
    if output_dir:
        config.download_dir = Path(output_dir)
    if audio_format:
        config.audio_format = audio_format
    if audio_quality:
        config.audio_quality = audio_quality
    if no_metadata:
        config.embed_metadata = False
    if no_artwork:
        config.embed_artwork = False
        config.save_artwork = False
    if overwrite:
        config.overwrite = True

    config.ensure_dirs()

    source = detect_source(url)
    if source == "unknown":
        print_error(f"Could not detect source from URL: {url}")
        print_info("Supported sources: YouTube, Spotify")
        sys.exit(1)

    output_path = config.download_dir

    if source == "youtube":
        files = download_youtube_url(url, output_path)
    elif source == "spotify":
        files = download_spotify_url(url, output_path)
    else:
        print_error(f"Unsupported source: {source}")
        sys.exit(1)

    print_download_summary(files, output_path)


@main.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--source", "-s", type=click.Choice(["youtube", "spotify", "all"]),
              default="all", help="Search source")
@click.option("--limit", "-l", type=int, default=10, help="Maximum results")
def search(query: tuple, source: str, limit: int) -> None:
    """Search for tracks on YouTube or Spotify."""
    query_str = " ".join(query)
    print_info(f"Searching for: {query_str}")

    results = []

    if source in ("youtube", "all"):
        yt_results = youtube_source.search(query_str, max_results=limit)
        for t in yt_results:
            t.source = "youtube"
        results.extend(yt_results)

    if source in ("spotify", "all"):
        sp_results = spotify_source.search(query_str, max_results=limit)
        for t in sp_results:
            t.source = "spotify"
        results.extend(sp_results)

    if not results:
        print_warning("No results found")
        return

    from musicgrab.utils import create_table

    table = create_table("Search Results", ["#", "Title", "Artist", "Source", "Duration"])
    for i, track in enumerate(results, 1):
        duration_str = format_duration(track.duration)
        table.add_row(
            str(i),
            track.title,
            track.artist,
            track.source,
            duration_str,
        )
    console.print(table)


@main.group()
def library() -> None:
    """Manage the local music library."""
    pass


@library.command("scan")
@click.option("--dir", "directory", type=click.Path(), default=None,
              help="Directory to scan (default: library directory)")
def library_scan(directory: Optional[str]) -> None:
    """Scan for audio files and add to library."""
    scan_dir = Path(directory) if directory else None
    tracks = library_manager.scan(scan_dir)
    if tracks:
        from musicgrab.utils import create_table

        table = create_table("Found Tracks", ["Title", "Artist", "Album", "Duration"])
        for track in tracks[:50]:  # Limit display
            table.add_row(
                track.title,
                track.artist,
                track.album or "-",
                format_duration(track.duration),
            )
        console.print(table)
        if len(tracks) > 50:
            print_info(f"... and {len(tracks) - 50} more")


@library.command("list")
def library_list() -> None:
    """List all tracks in the library."""
    library_manager.print_library()


@library.command("stats")
def library_stats() -> None:
    """Show library statistics."""
    library_manager.print_stats()


@library.command("organize")
@click.option("--dir", "directory", type=click.Path(), default=None,
              help="Directory to organize (default: library directory)")
def library_organize(directory: Optional[str]) -> None:
    """Organize tracks into artist/album folders."""
    target_dir = Path(directory) if directory else None
    library_manager.organize(target_dir)


@library.command("search")
@click.argument("query")
def library_search(query: str) -> None:
    """Search for tracks in the library."""
    results = library_manager.search(query)
    if not results:
        print_warning(f"No tracks found matching: {query}")
        return

    from musicgrab.utils import create_table

    table = create_table("Search Results", ["Title", "Artist", "Album", "Duration"])
    for track in results:
        table.add_row(
            track.title,
            track.artist,
            track.album or "-",
            format_duration(track.duration),
        )
    console.print(table)


@main.group()
def config_cmd() -> None:
    """Configure MusicGrab settings."""
    pass


@config_cmd.command("show")
def config_show() -> None:
    """Show current configuration."""
    from musicgrab.utils import create_table

    table = create_table("Configuration", ["Setting", "Value"])
    table.add_row("Download Directory", str(config.download_dir))
    table.add_row("Library Directory", str(config.library_dir))
    table.add_row("Audio Format", config.audio_format)
    table.add_row("Audio Quality", f"{config.audio_quality}kbps")
    table.add_row("Embed Metadata", str(config.embed_metadata))
    table.add_row("Embed Artwork", str(config.embed_artwork))
    table.add_row("Save Artwork", str(config.save_artwork))
    table.add_row("Overwrite", str(config.overwrite))
    table.add_row("Spotify Client ID", config.spotify_client_id or "(not set)")
    table.add_row("Spotify Client Secret", "****" if config.spotify_client_secret else "(not set)")
    console.print(table)


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value."""
    valid_keys = [
        "download_dir", "library_dir", "audio_format", "audio_quality",
        "embed_metadata", "embed_artwork", "save_artwork", "overwrite",
    ]
    if key not in valid_keys:
        print_error(f"Invalid key: {key}")
        print_info(f"Valid keys: {', '.join(valid_keys)}")
        sys.exit(1)

    if key in ("embed_metadata", "embed_artwork", "save_artwork", "overwrite"):
        value = value.lower() in ("true", "1", "yes", "on")
    elif key == "audio_quality":
        value = str(value)

    setattr(config, key, value)
    config.save()
    print_success(f"Set {key} = {value}")


@config_cmd.command("spotify")
def config_spotify() -> None:
    """Configure Spotify API credentials."""
    from musicgrab.config import configure_spotify
    configure_spotify()


@main.group()
def queue() -> None:
    """Manage the download queue."""
    pass


@queue.command("list")
def queue_list() -> None:
    """List items in the download queue."""
    download_queue.print_status()


@queue.command("save")
@click.option("--file", "-f", "file_path", type=click.Path(), default=None,
              help="File to save queue to")
def queue_save(file_path: Optional[str]) -> None:
    """Save the current queue to a file."""
    save_path = Path(file_path) if file_path else config.library_dir / "queue.json"
    download_queue.save(save_path)


@queue.command("load")
@click.option("--file", "-f", "file_path", type=click.Path(), default=None,
              help="File to load queue from")
def queue_load(file_path: Optional[str]) -> None:
    """Load a queue from a file."""
    load_path = Path(file_path) if file_path else config.library_dir / "queue.json"
    download_queue.load(load_path)


@queue.command("clear")
def queue_clear() -> None:
    """Clear all items from the queue."""
    download_queue.clear()
    print_success("Queue cleared")


@main.command()
def info() -> None:
    """Show system information and dependencies."""
    from musicgrab.utils import check_ffmpeg, check_yt_dlp, create_table

    table = create_table("System Information", ["Component", "Status"])
    table.add_row("MusicGrab", f"v{__version__}")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("ffmpeg", "✓ Installed" if check_ffmpeg() else "✗ Not found")
    table.add_row("yt-dlp", "✓ Installed" if check_yt_dlp() else "✗ Not found")
    table.add_row("Download Dir", str(config.download_dir))
    table.add_row("Library Dir", str(config.library_dir))
    table.add_row("Audio Format", config.audio_format)
    table.add_row("Audio Quality", f"{config.audio_quality}kbps")
    table.add_row("Spotify Configured", "✓ Yes" if config.spotify_client_id else "✗ No")
    console.print(table)


if __name__ == "__main__":
    main()
