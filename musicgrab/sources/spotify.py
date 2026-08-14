"""Spotify source module for MusicGrab.

Handles metadata extraction from Spotify via SpotifyScraper, which reads
the same public JSON data Spotify's own web player and embed pages use.
No developer app, Client ID/Secret, or Premium subscription is needed —
Spotify's official Web API now requires a Premium account just to
register an app (Feb 2026 policy change), so this is the only way to
resolve Spotify links/searches for a free-tier user.

Audio downloads are still handled via YouTube (search-based) since
Spotify does not provide direct audio download access either way.
"""

from typing import List, Optional

from spotify_scraper import SpotifyClient
from spotify_scraper.errors import SpotifyScraperError

from musicgrab.models.album import Album
from musicgrab.models.playlist import Playlist
from musicgrab.models.track import Track
from musicgrab.utils import extract_spotify_id, is_spotify_url


def _images_to_thumbnail(images) -> str:
    if not images:
        return ""
    # Images are pre-sorted largest-first by the library; take the first.
    return images[0].url


def _year_from_release_date(release_date) -> int:
    if not release_date:
        return 0
    try:
        return int(str(release_date)[:4])
    except ValueError:
        return 0


class SpotifySource:
    """Handles Spotify metadata extraction via SpotifyScraper (no auth required)."""

    def __init__(self, config) -> None:
        self.config = config
        self._client: Optional[SpotifyClient] = None

    def _get_client(self) -> SpotifyClient:
        if self._client is None:
            self._client = SpotifyClient()
        return self._client

    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid Spotify URL."""
        return is_spotify_url(url)

    def _scraper_track_to_track(self, t, *, album_title: str = "") -> Track:
        artists = [a.name for a in (t.artists or [])]
        artist = ", ".join(artists) if artists else "Unknown"
        album_name = album_title or (t.album.name if getattr(t, "album", None) else "")
        return Track(
            title=t.name or "Unknown",
            artist=artist,
            album=album_name,
            duration=(t.duration_ms or 0) / 1000.0,
            track_number=t.track_number or 0,
            year=_year_from_release_date(getattr(t, "release_date", None)),
            source="spotify",
            source_url=t.url or f"https://open.spotify.com/track/{t.id}",
            source_id=t.id or "",
            thumbnail_url=_images_to_thumbnail(t.images),
        )

    def parse_track(self, url: str) -> Track:
        """Parse a Spotify track URL into a Track object."""
        result = extract_spotify_id(url)
        if not result or result[0] != "track":
            raise ValueError(f"Not a Spotify track URL: {url}")

        try:
            t = self._get_client().get_track(url)
        except SpotifyScraperError as exc:
            raise ValueError(f"Failed to fetch Spotify track: {exc}") from exc

        return self._scraper_track_to_track(t)

    def parse_album(self, url: str) -> Album:
        """Parse a Spotify album URL into an Album object."""
        result = extract_spotify_id(url)
        if not result or result[0] != "album":
            raise ValueError(f"Not a Spotify album URL: {url}")

        try:
            a = self._get_client().get_album(url)
        except SpotifyScraperError as exc:
            raise ValueError(f"Failed to fetch Spotify album: {exc}") from exc

        artists = [ar.name for ar in (a.artists or [])]
        artist = ", ".join(artists) if artists else "Unknown"
        thumbnail_url = _images_to_thumbnail(a.images)

        album = Album(
            title=a.name or "Unknown",
            artist=artist,
            source="spotify",
            source_url=url,
            source_id=a.id or "",
            thumbnail_url=thumbnail_url,
            release_date=str(a.release_date) if a.release_date else "",
            total_tracks=a.total_tracks or 0,
        )

        for t in a.tracks or []:
            album.add_track(self._scraper_track_to_track(t, album_title=album.title))

        return album

    def parse_playlist(self, url: str) -> Playlist:
        """Parse a Spotify playlist URL into a Playlist object."""
        result = extract_spotify_id(url)
        if not result or result[0] != "playlist":
            raise ValueError(f"Not a Spotify playlist URL: {url}")

        try:
            p = self._get_client().get_playlist(url, max_tracks=None)
        except SpotifyScraperError as exc:
            raise ValueError(f"Failed to fetch Spotify playlist: {exc}") from exc

        playlist = Playlist(
            title=p.name or "Unknown Playlist",
            source="spotify",
            source_url=url,
            source_id=p.id or "",
            description=p.description or "",
            thumbnail_url=_images_to_thumbnail(p.images),
            owner=p.owner.name if p.owner else "",
            total_tracks=p.total_tracks or 0,
        )

        for item in p.tracks or []:
            track = getattr(item, "track", None)
            if not track:
                continue
            playlist.add_track(self._scraper_track_to_track(track))

        return playlist

    def search(self, query: str, max_results: int = 5) -> List[Track]:
        """Search for tracks on Spotify."""
        try:
            results = self._get_client().search(query, types=("track",), limit=max_results)
        except SpotifyScraperError:
            return []

        return [self._scraper_track_to_track(t) for t in (results.tracks or [])]

    def _artist_to_dict(self, artist) -> dict:
        return {
            "id": artist.id or "",
            "name": artist.name or "Unknown",
            "thumbnail_url": _images_to_thumbnail(artist.images),
            "url": artist.url or f"https://open.spotify.com/artist/{artist.id}",
        }

    def search_artist(self, query: str) -> Optional[dict]:
        """Search for an artist by name and return the best match (or None)."""
        try:
            results = self._get_client().search(query, types=("artist",), limit=1)
        except SpotifyScraperError:
            return None
        artists = results.artists or []
        return self._artist_to_dict(artists[0]) if artists else None

    def get_artist(self, url_or_id: str) -> Optional[dict]:
        """Resolve an artist URL/ID/name into {id, name, thumbnail_url, url}."""
        value = url_or_id if "open.spotify.com" in url_or_id else None
        try:
            if value:
                artist = self._get_client().get_artist(value)
            else:
                return self.search_artist(url_or_id)
        except SpotifyScraperError:
            return None
        return self._artist_to_dict(artist)

    def get_artist_top_tracks(self, artist_id: str, max_results: int = 10) -> List[Track]:
        """Top tracks for an artist, given their Spotify artist id."""
        try:
            artist = self._get_client().get_artist(f"https://open.spotify.com/artist/{artist_id}")
        except SpotifyScraperError:
            return []
        return [self._scraper_track_to_track(t) for t in (artist.top_tracks or [])][:max_results]

    def get_related_artists(self, artist_id: str, max_results: int = 10) -> List[dict]:
        """Artists related to the given Spotify artist id."""
        try:
            related = self._get_client().get_related_artists(
                f"https://open.spotify.com/artist/{artist_id}"
            )
        except SpotifyScraperError:
            return []
        return [self._artist_to_dict(a) for a in related[:max_results]]

    def get_latest_releases(self, artist_id: str, max_results: int = 5) -> List[dict]:
        """An artist's most recent releases (album/single name + artwork)."""
        try:
            releases = self._get_client().get_discography(
                f"https://open.spotify.com/artist/{artist_id}", max_releases=max_results
            )
        except SpotifyScraperError:
            return []
        return [
            {
                "id": r.id or "",
                "title": r.name or "Unknown",
                "thumbnail_url": _images_to_thumbnail(r.images),
                "url": f"https://open.spotify.com/album/{r.id}",
            }
            for r in releases
        ]
