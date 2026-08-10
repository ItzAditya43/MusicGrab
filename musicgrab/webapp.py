"""FastAPI web application for MusicGrab.

Wraps the existing musicgrab core (sources, library, metadata, artwork)
in a small JSON API and serves a single-page app frontend so the tool
can be used as a music web app instead of only a CLI.
"""

from __future__ import annotations

import hashlib
import mimetypes
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from musicgrab.artwork.saver import ArtworkSaver
from musicgrab.config import config
from musicgrab.library.manager import LibraryManager
from musicgrab.metadata.embedder import MetadataEmbedder
from musicgrab.models.playlist import Playlist
from musicgrab.sources.spotify import SpotifySource
from musicgrab.sources.youtube import YouTubeSource
from musicgrab.utils import ensure_ffmpeg, ensure_yt_dlp, is_spotify_url, is_youtube_url

config.ensure_dirs()

youtube_source = YouTubeSource(config)
spotify_source = SpotifySource(config)
metadata_embedder = MetadataEmbedder(config)
artwork_saver = ArtworkSaver(config)
library_manager = LibraryManager(config)

app = FastAPI(title="MusicGrab")

# ---------------------------------------------------------------------------
# In-memory job tracking for downloads (single-process; fine for a local app)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _track_id(track) -> str:
    """Stable id for a track based on its source, independent of library rescans."""
    key = f"{track.source}:{track.source_id or track.source_url}:{track.title}:{track.artist}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _track_to_public(track, tid: Optional[str] = None) -> dict:
    d = track.to_dict()
    d["id"] = tid or _track_id(track)
    d["has_audio"] = bool(track.output_path and Path(track.output_path).exists())
    return d


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _run_download_job(job_id: str, url: str) -> None:
    try:
        _update_job(job_id, status="running", message="Resolving URL...")
        output_dir = config.download_dir

        if is_youtube_url(url):
            _run_youtube_job(job_id, url, output_dir)
        elif is_spotify_url(url):
            _run_spotify_job(job_id, url, output_dir)
        else:
            _update_job(job_id, status="failed", message="Unrecognized URL (not YouTube or Spotify)")
            return
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, status="failed", message=str(exc))


def _run_youtube_job(job_id: str, url: str, output_dir: Path) -> None:
    if not ensure_yt_dlp() or not ensure_ffmpeg():
        _update_job(job_id, status="failed", message="yt-dlp or ffmpeg not installed on the server")
        return

    is_playlist = "playlist" in url or "list=" in url
    if is_playlist:
        playlist = youtube_source.parse_playlist(url)
        tracks = playlist.tracks
    else:
        tracks = [youtube_source.parse_video(url)]

    total = len(tracks)
    _update_job(job_id, total=total, done=0, message=f"Downloading {total} track(s)...")

    completed_tracks = []
    for i, track in enumerate(tracks, 1):
        if track.thumbnail_url:
            artwork_saver.load_artwork_into_track(track)

        dest_dir = output_dir
        if is_playlist:
            from musicgrab.utils import sanitize_path_component

            dest_dir = output_dir / sanitize_path_component(playlist.title)

        file_path = youtube_source.download_track(track, dest_dir)
        if file_path and config.embed_metadata:
            metadata_embedder.embed(track, file_path)
        if file_path and config.save_artwork:
            artwork_saver.save_artwork(track, dest_dir / "artwork")

        if file_path:
            library_manager.add_track(track)
            completed_tracks.append(track)

        _update_job(job_id, done=i, message=f"Downloaded {i}/{total}: {track.display_title}")

    _update_job(
        job_id,
        status="completed",
        message=f"Downloaded {len(completed_tracks)}/{total} track(s)",
        tracks=[_track_to_public(t) for t in completed_tracks],
    )


def _run_spotify_job(job_id: str, url: str, output_dir: Path) -> None:
    from musicgrab.utils import sanitize_path_component

    content_type = "playlist" if "playlist" in url else ("album" if "album" in url else "track")

    if content_type == "playlist":
        playlist = spotify_source.parse_playlist(url)
        source_tracks = playlist.tracks
        dest_dir = output_dir / sanitize_path_component(playlist.title)
    elif content_type == "album":
        album = spotify_source.parse_album(url)
        source_tracks = album.tracks
        dest_dir = output_dir / sanitize_path_component(f"{album.artist} - {album.title}")
    else:
        source_tracks = [spotify_source.parse_track(url)]
        dest_dir = output_dir

    total = len(source_tracks)
    _update_job(job_id, total=total, done=0, message=f"Matching {total} track(s) on YouTube...")

    if not (ensure_yt_dlp() and ensure_ffmpeg()):
        _update_job(job_id, status="failed", message="yt-dlp or ffmpeg not installed on the server")
        return

    completed_tracks = []
    for i, track in enumerate(source_tracks, 1):
        if track.thumbnail_url:
            artwork_saver.load_artwork_into_track(track)

        search_query = f"{track.artist} {track.title}"
        results = youtube_source.search(search_query, max_results=1)
        if not results:
            _update_job(job_id, done=i, message=f"Not found: {track.display_title}")
            continue

        yt_track = results[0]
        for field in ("title", "artist", "album", "duration", "track_number",
                      "disc_number", "year", "genre", "thumbnail_url", "thumbnail_data"):
            setattr(yt_track, field, getattr(track, field))

        file_path = youtube_source.download_track(yt_track, dest_dir)
        if file_path and config.embed_metadata:
            metadata_embedder.embed(yt_track, file_path)
        if file_path and config.save_artwork:
            artwork_saver.save_artwork(yt_track, dest_dir / "artwork")

        if file_path:
            library_manager.add_track(yt_track)
            completed_tracks.append(yt_track)

        _update_job(job_id, done=i, message=f"Downloaded {i}/{total}: {track.display_title}")

    _update_job(
        job_id,
        status="completed",
        message=f"Downloaded {len(completed_tracks)}/{total} track(s)",
        tracks=[_track_to_public(t) for t in completed_tracks],
    )


class DownloadRequest(BaseModel):
    url: str


@app.post("/api/downloads")
def start_download(req: DownloadRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "url is required")
    if not (is_youtube_url(url) or is_spotify_url(url)):
        raise HTTPException(400, "Only YouTube and Spotify URLs are supported")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "status": "queued",
            "message": "Queued",
            "done": 0,
            "total": 0,
            "created_at": time.time(),
            "tracks": [],
        }

    thread = threading.Thread(target=_run_download_job, args=(job_id, url), daemon=True)
    thread.start()
    return _jobs[job_id]


@app.get("/api/downloads")
def list_jobs():
    with _jobs_lock:
        return sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)


@app.get("/api/downloads/{job_id}")
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@app.get("/api/search")
def search(q: str, source: str = "all", limit: int = 15):
    if not q.strip():
        return {"results": []}

    results = []
    if source in ("youtube", "all"):
        for t in youtube_source.search(q, max_results=limit):
            t.source = "youtube"
            results.append(_track_to_public(t))
    if source in ("spotify", "all") and config.get_spotify_credentials():
        for t in spotify_source.search(q, max_results=limit):
            t.source = "spotify"
            results.append(_track_to_public(t))
    return {"results": results}


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@app.get("/api/library")
def get_library():
    tracks = library_manager.list_tracks()
    return {"tracks": [_track_to_public(t) for t in tracks]}


@app.post("/api/library/scan")
def scan_library():
    tracks = library_manager.scan()
    return {"tracks": [_track_to_public(t) for t in tracks]}


@app.get("/api/library/stats")
def library_stats():
    return library_manager.get_stats()


def _find_track_by_id(tid: str):
    for t in library_manager.list_tracks():
        if _track_id(t) == tid:
            return t
    return None


@app.get("/api/stream/{track_id}")
def stream_track(track_id: str):
    track = _find_track_by_id(track_id)
    if not track or not track.output_path:
        raise HTTPException(404, "Track not found")
    path = Path(track.output_path)
    if not path.exists():
        raise HTTPException(404, "Audio file not found")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/api/artwork/{track_id}")
def track_artwork(track_id: str):
    track = _find_track_by_id(track_id)
    if not track or not track.output_path:
        raise HTTPException(404, "Track not found")
    path = Path(track.output_path)
    artwork_dir = path.parent / "artwork"
    if artwork_dir.exists():
        stem_matches = list(artwork_dir.glob(f"{path.stem}.*"))
        if stem_matches:
            return FileResponse(stem_matches[0])
    raise HTTPException(404, "No artwork found")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConfigUpdate(BaseModel):
    audio_format: Optional[str] = None
    audio_quality: Optional[str] = None
    embed_metadata: Optional[bool] = None
    save_artwork: Optional[bool] = None
    spotify_client_id: Optional[str] = None
    spotify_client_secret: Optional[str] = None


@app.get("/api/config")
def get_config_api():
    return {
        "download_dir": str(config.download_dir),
        "library_dir": str(config.library_dir),
        "audio_format": config.audio_format,
        "audio_quality": config.audio_quality,
        "embed_metadata": config.embed_metadata,
        "save_artwork": config.save_artwork,
        "spotify_configured": bool(config.spotify_client_id),
    }


@app.post("/api/config")
def update_config(update: ConfigUpdate):
    data = update.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(config, key, value)
    config.save()
    return get_config_api()


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

_WEB_DIR = Path(__file__).parent / "web"
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="frontend")


def run() -> None:
    """Entry point for `musicgrab-web`."""
    import uvicorn

    uvicorn.run("musicgrab.webapp:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run()
