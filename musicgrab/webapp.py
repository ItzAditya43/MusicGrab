"""FastAPI web application for MusicGrab.

Wraps the existing musicgrab core (sources, library, metadata, artwork)
in a small JSON API and serves a single-page app frontend so the tool
can be used as a music web app instead of only a CLI.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import sys
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


def _init_track_status(job_id: str, tracks) -> None:
    """Seed the job's per-track list, all "queued", as soon as the full
    track list is known — before any downloading starts — so the UI can
    immediately show the whole batch instead of only what's finished.
    """
    _update_job(
        job_id,
        track_status=[
            {"title": t.title, "artist": t.artist, "status": "queued"} for t in tracks
        ],
    )


def _set_track_status(job_id: str, index: int, status: str) -> None:
    """status: 'queued' | 'active' | 'done' | 'skipped' | 'failed'"""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job and 0 <= index < len(job.get("track_status", [])):
            job["track_status"][index]["status"] = status


def _job_selected_indices(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return job.get("selected_indices") if job else None


def _wait_while_paused(job_id: str) -> bool:
    """Blocks while the job is paused. Deleting a job (see the DELETE
    endpoint) removes it from _jobs outright rather than tracking a
    separate cancel flag — cheaper to check and correct either way,
    since a job that no longer exists can't be resumed regardless.
    Returns True if the job was deleted while waiting (or is already
    gone), meaning the caller must stop immediately.
    """
    while True:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return True
            if not job.get("paused"):
                return False
        time.sleep(0.5)


def _job_alive(job_id: str) -> bool:
    with _jobs_lock:
        return job_id in _jobs


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


def _save_lyrics_sidecar(track, file_path: Path) -> None:
    """Best-effort: fetch lyrics and save them next to the downloaded audio
    file (same base name, .lrc/.txt extension) so any player that reads
    sidecar lyric files picks them up automatically, without the user
    having to open each track and click "Save .lrc" one at a time.

    Never raises — a lyrics lookup failing must not fail the download
    itself, especially mid-playlist where one bad lookup shouldn't stop
    the rest of the batch.
    """
    try:
        result = _fetch_lyrics(track, _track_id(track))
        if not result["found"]:
            return
        sidecar = file_path.with_suffix(".lrc" if result["synced_raw"] else ".txt")
        content = result["synced_raw"] or result["plain"]
        sidecar.write_text(content, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# A hard wall-clock ceiling per track, enforced at the loop level rather
# than inside individual network calls. `requests`' own timeout= only
# bounds the gap *between* reads, not a request's total duration — a
# slowly-trickling response (or any other call whose own timeout doesn't
# actually cover every way it can stall) can still block for a very long
# time despite every individual call looking "protected". A 775-track
# playlist download once hung on track 16 for 20+ minutes and never
# recovered even with per-call timeouts in place; this is the backstop
# that guarantees no single track can ever stall the rest of the batch.
_TRACK_TIMEOUT = 300


class _TrackTimeout(Exception):
    pass


def _run_with_timeout(fn, *args, timeout: int = _TRACK_TIMEOUT):
    """Run fn(*args), aborting the wait after `timeout` seconds.

    Plain threading.Thread + Event, deliberately not ThreadPoolExecutor:
    creating hundreds of short-lived executors over a long-running server
    process was empirically reproduced (in an isolated PyInstaller-frozen
    repro) to interact badly with concurrent.futures' global shutdown
    bookkeeping and stop reliably firing future.result()'s timeout after
    enough iterations — exactly matching a real 775-track playlist
    hanging at unpredictable points despite this same timeout logic
    "working" in short-lived test scripts. A raw Thread + Event has no
    such shared global state per-instance.

    Python threads can't be forcibly killed, so a timed-out call keeps
    running in the background rather than actually stopping — accepted
    since the alternative (the whole job loop blocked forever) is worse,
    and a leaked thread is self-contained and never blocks the batch.
    """
    result_box: dict = {}
    done = threading.Event()

    def _target():
        try:
            result_box["value"] = fn(*args)
        except Exception as exc:  # noqa: BLE001
            result_box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_target, daemon=True).start()
    if not done.wait(timeout=timeout):
        raise _TrackTimeout(f"timed out after {timeout}s")
    if "error" in result_box:
        raise result_box["error"]
    return result_box["value"]


def _process_youtube_track(track, dest_dir: Path) -> Optional[Path]:
    if track.thumbnail_url:
        artwork_saver.load_artwork_into_track(track)
    file_path = youtube_source.download_track(track, dest_dir)
    if file_path and config.embed_metadata:
        metadata_embedder.embed(track, file_path)
    if file_path and config.save_artwork:
        artwork_saver.save_artwork(track, dest_dir / "artwork")
    if file_path:
        _save_lyrics_sidecar(track, file_path)
        library_manager.add_track(track)
    return file_path


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
    _init_track_status(job_id, tracks)

    dest_dir = output_dir
    if is_playlist:
        from musicgrab.utils import sanitize_path_component

        dest_dir = output_dir / sanitize_path_component(playlist.title)

    selected = _job_selected_indices(job_id)
    completed_tracks = []
    for idx, track in enumerate(tracks):
        i = idx + 1
        if selected is not None and idx not in selected:
            _set_track_status(job_id, idx, "skipped")
            _update_job(job_id, done=i)
            continue
        if _wait_while_paused(job_id):
            return
        _set_track_status(job_id, idx, "active")
        try:
            file_path = _run_with_timeout(_process_youtube_track, track, dest_dir)
        except _TrackTimeout:
            file_path = None
            _set_track_status(job_id, idx, "failed")
            _update_job(job_id, done=i, message=f"Timed out, skipping: {track.display_title}")
        except Exception:  # noqa: BLE001
            file_path = None
            _set_track_status(job_id, idx, "failed")
            _update_job(job_id, done=i, message=f"Failed, skipping: {track.display_title}")
        else:
            if file_path:
                completed_tracks.append(track)
                _set_track_status(job_id, idx, "done")
            else:
                _set_track_status(job_id, idx, "failed")
            _update_job(job_id, done=i, message=f"Downloaded {i}/{total}: {track.display_title}")

    if not _job_alive(job_id):
        return
    _update_job(
        job_id,
        status="completed",
        message=f"Downloaded {len(completed_tracks)}/{total} track(s)",
        tracks=[_track_to_public(t) for t in completed_tracks],
    )


def _process_spotify_track(track, dest_dir: Path):
    if track.thumbnail_url:
        artwork_saver.load_artwork_into_track(track)

    search_query = f"{track.artist} {track.title}"
    results = youtube_source.search(search_query, max_results=1)
    if not results:
        return None, None

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
        _save_lyrics_sidecar(yt_track, file_path)
        library_manager.add_track(yt_track)
    return file_path, yt_track


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
    _init_track_status(job_id, source_tracks)

    if not (ensure_yt_dlp() and ensure_ffmpeg()):
        _update_job(job_id, status="failed", message="yt-dlp or ffmpeg not installed on the server")
        return

    selected = _job_selected_indices(job_id)
    completed_tracks = []
    for idx, track in enumerate(source_tracks):
        i = idx + 1
        if selected is not None and idx not in selected:
            _set_track_status(job_id, idx, "skipped")
            _update_job(job_id, done=i)
            continue
        if _wait_while_paused(job_id):
            return
        _set_track_status(job_id, idx, "active")
        try:
            file_path, yt_track = _run_with_timeout(_process_spotify_track, track, dest_dir)
        except _TrackTimeout:
            file_path = None
            _set_track_status(job_id, idx, "failed")
            _update_job(job_id, done=i, message=f"Timed out, skipping: {track.display_title}")
        except Exception:  # noqa: BLE001
            file_path = None
            _set_track_status(job_id, idx, "failed")
            _update_job(job_id, done=i, message=f"Failed, skipping: {track.display_title}")
        else:
            if not file_path:
                _set_track_status(job_id, idx, "skipped")
                _update_job(job_id, done=i, message=f"Not found: {track.display_title}")
                continue
            completed_tracks.append(yt_track)
            _set_track_status(job_id, idx, "done")
            _update_job(job_id, done=i, message=f"Downloaded {i}/{total}: {track.display_title}")

    if not _job_alive(job_id):
        return
    _update_job(
        job_id,
        status="completed",
        message=f"Downloaded {len(completed_tracks)}/{total} track(s)",
        tracks=[_track_to_public(t) for t in completed_tracks],
    )


class DownloadRequest(BaseModel):
    url: str
    # None = download every track. When set, tracks whose index isn't in
    # this list are marked "skipped" instead of processed — lets the UI
    # offer a pick-which-tracks step for playlists/albums before a bulk
    # download starts.
    selected_indices: Optional[list[int]] = None


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
            # Live per-track breakdown so the UI can show what's done, what's
            # currently in progress, and what's still queued — not just a
            # single rolling message string for the whole job.
            "track_status": [],
            "paused": False,
            "selected_indices": set(req.selected_indices) if req.selected_indices is not None else None,
        }

    thread = threading.Thread(target=_run_download_job, args=(job_id, url), daemon=True)
    thread.start()
    return _jobs[job_id]


class PreviewRequest(BaseModel):
    url: str


@app.post("/api/downloads/preview")
def preview_download(req: PreviewRequest):
    """List the tracks a URL would expand to, without starting a download —
    lets the UI show a pick-which-tracks step before a bulk (playlist/album)
    download kicks off."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "url is required")

    if is_youtube_url(url):
        is_playlist = "playlist" in url or "list=" in url
        if is_playlist:
            playlist = youtube_source.parse_playlist(url)
            tracks, title = playlist.tracks, playlist.title
        else:
            tracks = [youtube_source.parse_video(url)]
            title = tracks[0].title if tracks else url
    elif is_spotify_url(url):
        content_type = "playlist" if "playlist" in url else ("album" if "album" in url else "track")
        if content_type == "playlist":
            playlist = spotify_source.parse_playlist(url)
            tracks, title = playlist.tracks, playlist.title
        elif content_type == "album":
            album = spotify_source.parse_album(url)
            tracks, title = album.tracks, f"{album.artist} - {album.title}"
        else:
            tracks = [spotify_source.parse_track(url)]
            title = tracks[0].title if tracks else url
    else:
        raise HTTPException(400, "Only YouTube and Spotify URLs are supported")

    return {
        "title": title,
        "tracks": [
            {"index": i, "title": t.title, "artist": t.artist, "duration": t.duration}
            for i, t in enumerate(tracks)
        ],
    }


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


@app.post("/api/downloads/{job_id}/pause")
def pause_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job["status"] not in ("queued", "running"):
            raise HTTPException(400, "Job isn't running")
        job["paused"] = True
    return job


@app.post("/api/downloads/{job_id}/resume")
def resume_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job["paused"] = False
    return job


@app.delete("/api/downloads/{job_id}")
def delete_job(job_id: str):
    # Removing the job outright (rather than a separate cancel flag) is
    # also the signal the worker thread's own loop checks to stop — see
    # _wait_while_paused / _job_alive. A background thread mid-track will
    # finish that one track (Python threads can't be force-killed, same
    # tradeoff as the per-track timeout) but stops before starting the
    # next, and all its further writes silently no-op since the job's gone.
    with _jobs_lock:
        existed = _jobs.pop(job_id, None) is not None
    if not existed:
        raise HTTPException(404, "Job not found")
    return {"deleted": True}


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
    if source in ("spotify", "all"):
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
    # Downloads land in download_dir; library_dir is where `library organize`
    # files end up. Scan both so the web app's "Rescan" picks up everything
    # regardless of which directory a track happens to live in. Safe to run
    # both — scan() only replaces entries under the directory it scanned.
    library_manager.scan(config.download_dir)
    if config.library_dir != config.download_dir:
        library_manager.scan(config.library_dir)
    return {"tracks": [_track_to_public(t) for t in library_manager.list_tracks()]}


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
# Discover: recommendations + followed artists (Spotify-backed, no auth)
# ---------------------------------------------------------------------------

_FOLLOWED_ARTISTS_FILE = "followed_artists.json"


def _followed_artists_path() -> Path:
    return config.library_dir / _FOLLOWED_ARTISTS_FILE


def _load_followed_artists() -> list[dict]:
    path = _followed_artists_path()
    if not path.exists():
        return []
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_followed_artists(artists: list[dict]) -> None:
    import json

    config.library_dir.mkdir(parents=True, exist_ok=True)
    _followed_artists_path().write_text(json.dumps(artists, indent=2), encoding="utf-8")


@app.get("/api/discover/recommended")
def discover_recommended(limit: int = 20):
    """Tracks similar to what's already in the library, via Spotify's
    "related artists" for a handful of artists you've actually downloaded.
    """
    library_tracks = library_manager.list_tracks()
    seed_artists = []
    seen = set()
    for t in library_tracks:
        name = (t.artist or "").split(",")[0].strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            seed_artists.append(name)
        if len(seed_artists) >= 3:
            break

    if not seed_artists:
        return {"tracks": [], "based_on": []}

    library_titles = {(t.artist or "", t.title or "") for t in library_tracks}
    results = []
    seen_track_keys = set()
    for name in seed_artists:
        artist = spotify_source.search_artist(name)
        if not artist or not artist["id"]:
            continue
        related = spotify_source.get_related_artists(artist["id"], max_results=3)
        for rel in related:
            if not rel["id"]:
                continue
            for track in spotify_source.get_artist_top_tracks(rel["id"], max_results=3):
                key = (track.artist, track.title)
                if key in library_titles or key in seen_track_keys:
                    continue
                seen_track_keys.add(key)
                track.source = "spotify"
                results.append(_track_to_public(track))
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    return {"tracks": results, "based_on": seed_artists}


@app.get("/api/artists/followed")
def list_followed_artists():
    followed = _load_followed_artists()
    for artist in followed:
        artist["latest_releases"] = spotify_source.get_latest_releases(artist["id"], max_results=3)
    return {"artists": followed}


class FollowArtistRequest(BaseModel):
    query: str


@app.post("/api/artists/follow")
def follow_artist(req: FollowArtistRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "query is required")

    artist = spotify_source.get_artist(query)
    if not artist or not artist["id"]:
        raise HTTPException(404, "Artist not found")

    followed = _load_followed_artists()
    if not any(a["id"] == artist["id"] for a in followed):
        followed.append(artist)
        _save_followed_artists(followed)
    return artist


@app.delete("/api/artists/{artist_id}/follow")
def unfollow_artist(artist_id: str):
    followed = [a for a in _load_followed_artists() if a["id"] != artist_id]
    _save_followed_artists(followed)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Lyrics (via lrclib.net — free, keyless, provides synced + plain lyrics)
# ---------------------------------------------------------------------------

_lyrics_cache: dict[str, dict] = {}

LRCLIB_GET_API = "https://lrclib.net/api/get"
LRCLIB_SEARCH_API = "https://lrclib.net/api/search"

_JUNK_PATTERN = re.compile(
    r"""\(?\[?\s*(official\s*(music\s*)?video|official\s*audio|official\s*lyric\s*video|
    lyric\s*video|lyrics|remastered(\s*\d{4})?|hd|hq|4k|visualizer|audio\s*only|
    full\s*song|explicit)\s*\)?\]?""",
    re.IGNORECASE | re.VERBOSE,
)
_ARTIST_JUNK_SUFFIXES = (" - topic", " official", " vevo")


def _clean_lyrics_query(title: str, artist: str) -> tuple[str, str]:
    """Strip YouTube-metadata junk so lrclib's search can actually match.

    YouTube titles/uploaders are messy ("Queen Official" / "Song (Official
    Video Remastered)") and lrclib's exact-match /get endpoint needs clean
    track/artist names, so leaving this junk in silently returns no lyrics
    for almost every YouTube-sourced track.
    """
    clean_title = _JUNK_PATTERN.sub("", title)
    clean_title = re.sub(r"[\(\[]\s*[\)\]]", "", clean_title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip(" -")

    clean_artist = artist
    for suffix in _ARTIST_JUNK_SUFFIXES:
        if clean_artist.lower().endswith(suffix):
            clean_artist = clean_artist[: -len(suffix)]
    clean_artist = clean_artist.strip()

    return clean_title or title, clean_artist or artist


def _parse_synced_lyrics(raw: str) -> list[dict]:
    """Parse LRC-format `[mm:ss.xx] line` text into [{time, text}, ...]."""
    import re

    lines = []
    pattern = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
    for line in raw.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        minutes, seconds, text = match.groups()
        t = int(minutes) * 60 + float(seconds)
        text = text.strip()
        if text:
            lines.append({"time": t, "text": text})
    return lines


def _fetch_lyrics(track, cache_key: str) -> dict:
    """Look up lyrics for a track on lrclib.net, caching the raw result.

    Cache holds `synced_raw` (LRC text) alongside the parsed form so the
    .lrc download endpoint can reuse the exact same lookup instead of
    hitting lrclib a second time.
    """
    if cache_key in _lyrics_cache:
        return _lyrics_cache[cache_key]

    import requests

    clean_title, clean_artist = _clean_lyrics_query(track.title, track.artist)

    params = {"track_name": clean_title, "artist_name": clean_artist}
    if track.album:
        params["album_name"] = track.album
    if track.duration:
        params["duration"] = int(track.duration)

    data = None
    try:
        resp = requests.get(LRCLIB_GET_API, params=params, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
    except requests.RequestException:
        pass

    # The exact-match /get endpoint needs a precise duration/title match,
    # which YouTube-sourced tracks rarely have (intro/outro padding, junky
    # titles). Fall back to fuzzy /search and take the closest hit.
    if not data or not (data.get("plainLyrics") or data.get("syncedLyrics")):
        try:
            resp = requests.get(
                LRCLIB_SEARCH_API,
                params={"track_name": clean_title, "artist_name": clean_artist},
                timeout=8,
            )
            if resp.status_code == 200:
                results = resp.json()
                data = results[0] if results else None
        except requests.RequestException:
            data = None

    if not data:
        result = {"found": False, "plain": None, "synced": None, "synced_raw": None}
        _lyrics_cache[cache_key] = result
        return result

    plain = data.get("plainLyrics") or None
    synced_raw = data.get("syncedLyrics") or None
    result = {
        "found": bool(plain or synced_raw),
        "plain": plain,
        "synced": _parse_synced_lyrics(synced_raw) if synced_raw else None,
        "synced_raw": synced_raw,
    }
    _lyrics_cache[cache_key] = result
    return result


@app.get("/api/lyrics/{track_id}")
def track_lyrics(track_id: str):
    track = _find_track_by_id(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    result = _fetch_lyrics(track, track_id)
    return {k: v for k, v in result.items() if k != "synced_raw"}


@app.get("/api/lyrics/{track_id}/download")
def download_lyrics(track_id: str):
    track = _find_track_by_id(track_id)
    if not track:
        raise HTTPException(404, "Track not found")

    result = _fetch_lyrics(track, track_id)
    if not result["found"]:
        raise HTTPException(404, "No lyrics found for this track")

    from urllib.parse import quote

    from fastapi.responses import Response

    from musicgrab.utils import sanitize_path_component

    safe_name = sanitize_path_component(f"{track.artist} - {track.title}")
    # Content-Disposition header values must be latin-1; track names can
    # contain arbitrary unicode (e.g. YouTube titles with "–" or emoji), so
    # use an ASCII-only fallback filename plus the RFC 5987 filename* form
    # for browsers that render the real one.
    ascii_name = safe_name.encode("ascii", "ignore").decode("ascii").strip() or "lyrics"

    def _disposition(ext: str) -> str:
        return f"attachment; filename=\"{ascii_name}{ext}\"; filename*=UTF-8''{quote(safe_name + ext)}"

    if result["synced_raw"]:
        return Response(
            content=result["synced_raw"],
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _disposition(".lrc")},
        )
    return Response(
        content=result["plain"],
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": _disposition(".txt")},
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConfigUpdate(BaseModel):
    audio_format: Optional[str] = None
    audio_quality: Optional[str] = None
    embed_metadata: Optional[bool] = None
    save_artwork: Optional[bool] = None


@app.get("/api/config")
def get_config_api():
    return {
        "download_dir": str(config.download_dir),
        "library_dir": str(config.library_dir),
        "audio_format": config.audio_format,
        "audio_quality": config.audio_quality,
        "embed_metadata": config.embed_metadata,
        "save_artwork": config.save_artwork,
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

def _web_dir() -> Path:
    # When frozen by PyInstaller (for the Tauri desktop build), bundled data
    # files are extracted under sys._MEIPASS instead of living next to this
    # source file.
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / "musicgrab" / "web"
    return Path(__file__).parent / "web"


_WEB_DIR = _web_dir()
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="frontend")


def run() -> None:
    """Entry point for `musicgrab-web` (also used as the Tauri sidecar entry point)."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run()
