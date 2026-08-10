"""Spotify source module for MusicGrab.

Handles metadata extraction from Spotify using the Spotify Web API.
For Spotify, this module extracts metadata, artwork, and track listings.
Audio downloads are handled via YouTube (search-based) since Spotify does
not provide direct audio download access.
"""

import base64
import json
import time
from pathlib import Path
from typing import List, Optional

import requests

from musicgrab.models.album import Album
from musicgrab.models.playlist import Playlist
from musicgrab.models.track import Track
from musicgrab.utils import (
    console,
    extract_spotify_id,
    is_spotify_url,
    print_error,
    print_info,
    print_success,
    print_warning,
    sanitize_path_component,
)


class SpotifySource:
    """Handles Spotify metadata extraction via the Spotify Web API."""

    API_BASE = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self, config) -> None:
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid Spotify URL."""
        return is_spotify_url(url)

    def _get_access_token(self) -> Optional[str]:
        """Get or refresh the Spotify access token."""
        if self._access_token and time.time() < self._token_expires:
            return self._access_token

        creds = self.config.get_spotify_credentials()
        if not creds:
            print_error("Spotify credentials not configured.")
            print_info("Run: musicgrab config spotify")
            print_info("Or set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET env vars")
            return None

        client_id = creds["client_id"]
        client_secret = creds["client_secret"]

        auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        response = requests.post(self.TOKEN_URL, headers=headers, data=data)
        if response.status_code != 200:
            print_error(f"Failed to authenticate with Spotify: {response.text}")
            return None

        token_data = response.json()
        self._access_token = token_data["access_token"]
        self._token_expires = time.time() + token_data.get("expires_in", 3600) - 60
        return self._access_token

    def _api_request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a request to the Spotify API."""
        token = self._get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.API_BASE}{endpoint}"

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print_error(f"Spotify API error: {response.status_code} - {response.text}")
            return None

        return response.json()

    def parse_track(self, url: str) -> Track:
        """Parse a Spotify track URL into a Track object."""
        result = extract_spotify_id(url)
        if not result:
            return Track(title="Unknown", artist="Unknown", source="spotify", source_url=url)

        track_type, track_id = result
        if track_type != "track":
            return Track(title="Unknown", artist="Unknown", source="spotify", source_url=url)

        data = self._api_request(f"/tracks/{track_id}")
        if not data:
            return Track(title="Unknown", artist="Unknown", source="spotify", source_url=url)

        artists = [a["name"] for a in data.get("artists", [])]
        artist = ", ".join(artists) if artists else "Unknown"
        title = data.get("name", "Unknown")
        album_data = data.get("album", {})
        album_name = album_data.get("name", "")
        duration_ms = data.get("duration_ms", 0)
        duration = duration_ms / 1000.0
        track_number = data.get("track_number", 0)
        disc_number = data.get("disc_number", 0)
        year = int(album_data.get("release_date", "0")[:4]) if album_data.get("release_date") else 0
        genres = album_data.get("genres", [])
        genre = ", ".join(genres) if genres else ""

        # Get thumbnail
        images = album_data.get("images", [])
        thumbnail_url = images[0]["url"] if images else ""

        track = Track(
            title=title,
            artist=artist,
            album=album_name,
            duration=duration,
            track_number=track_number,
            disc_number=disc_number,
            year=year,
            genre=genre,
            source="spotify",
            source_url=url,
            source_id=track_id,
            thumbnail_url=thumbnail_url,
        )
        return track

    def parse_album(self, url: str) -> Album:
        """Parse a Spotify album URL into an Album object."""
        result = extract_spotify_id(url)
        if not result:
            return Album(title="Unknown", source="spotify", source_url=url)

        album_type, album_id = result
        if album_type != "album":
            return Album(title="Unknown", source="spotify", source_url=url)

        data = self._api_request(f"/albums/{album_id}")
        if not data:
            return Album(title="Unknown", source="spotify", source_url=url)

        artists = [a["name"] for a in data.get("artists", [])]
        artist = ", ".join(artists) if artists else "Unknown"
        title = data.get("name", "Unknown")
        description = data.get("description", "")
        release_date = data.get("release_date", "")
        genres = data.get("genres", [])
        images = data.get("images", [])
        thumbnail_url = images[0]["url"] if images else ""

        album = Album(
            title=title,
            artist=artist,
            source="spotify",
            source_url=url,
            source_id=album_id,
            description=description,
            thumbnail_url=thumbnail_url,
            release_date=release_date,
            genres=genres,
        )

        # Parse tracks
        tracks_data = data.get("tracks", {}).get("items", [])
        for i, track_data in enumerate(tracks_data):
            track_artists = [a["name"] for a in track_data.get("artists", [])]
            track_artist = ", ".join(track_artists) if track_artists else artist
            track_title = track_data.get("name", "Unknown")
            duration_ms = track_data.get("duration_ms", 0)
            duration = duration_ms / 1000.0
            track_number = track_data.get("track_number", i + 1)
            disc_number = track_data.get("disc_number", 1)

            track = Track(
                title=track_title,
                artist=track_artist,
                album=title,
                duration=duration,
                track_number=track_number,
                disc_number=disc_number,
                year=int(release_date[:4]) if release_date else 0,
                genre=", ".join(genres) if genres else "",
                source="spotify",
                source_url=f"https://open.spotify.com/track/{track_data.get('id', '')}",
                source_id=track_data.get("id", ""),
                thumbnail_url=thumbnail_url,
            )
            album.add_track(track)

        return album

    def parse_playlist(self, url: str) -> Playlist:
        """Parse a Spotify playlist URL into a Playlist object."""
        result = extract_spotify_id(url)
        if not result:
            return Playlist(title="Unknown Playlist", source="spotify", source_url=url)

        playlist_type, playlist_id = result
        if playlist_type != "playlist":
            return Playlist(title="Unknown Playlist", source="spotify", source_url=url)

        data = self._api_request(f"/playlists/{playlist_id}")
        if not data:
            return Playlist(title="Unknown Playlist", source="spotify", source_url=url)

        title = data.get("name", "Unknown Playlist")
        description = data.get("description", "")
        owner = data.get("owner", {}).get("display_name", "")
        images = data.get("images", [])
        thumbnail_url = images[0]["url"] if images else ""

        playlist = Playlist(
            title=title,
            source="spotify",
            source_url=url,
            source_id=playlist_id,
            description=description,
            thumbnail_url=thumbnail_url,
            owner=owner,
        )

        # Parse tracks (handle pagination)
        tracks_data = data.get("tracks", {}).get("items", [])
        for item in tracks_data:
            track_data = item.get("track", {})
            if not track_data:
                continue

            artists = [a["name"] for a in track_data.get("artists", [])]
            artist = ", ".join(artists) if artists else "Unknown"
            track_title = track_data.get("name", "Unknown")
            album_data = track_data.get("album", {})
            album_name = album_data.get("name", "")
            duration_ms = track_data.get("duration_ms", 0)
            duration = duration_ms / 1000.0
            track_number = track_data.get("track_number", 0)
            disc_number = track_data.get("disc_number", 0)
            release_date = album_data.get("release_date", "")
            year = int(release_date[:4]) if release_date else 0
            genres = album_data.get("genres", [])
            genre = ", ".join(genres) if genres else ""

            images = album_data.get("images", [])
            thumbnail = images[0]["url"] if images else thumbnail_url

            track = Track(
                title=track_title,
                artist=artist,
                album=album_name,
                duration=duration,
                track_number=track_number,
                disc_number=disc_number,
                year=year,
                genre=genre,
                source="spotify",
                source_url=f"https://open.spotify.com/track/{track_data.get('id', '')}",
                source_id=track_data.get("id", ""),
                thumbnail_url=thumbnail,
            )
            playlist.add_track(track)

        return playlist

    def search(self, query: str, max_results: int = 5) -> List[Track]:
        """Search for tracks on Spotify."""
        params = {
            "q": query,
            "type": "track",
            "limit": max_results,
        }
        data = self._api_request("/search", params)
        if not data:
            return []

        tracks = []
        for item in data.get("tracks", {}).get("items", []):
            artists = [a["name"] for a in item.get("artists", [])]
            artist = ", ".join(artists) if artists else "Unknown"
            title = item.get("name", "Unknown")
            duration_ms = item.get("duration_ms", 0)
            duration = duration_ms / 1000.0
            album_data = item.get("album", {})
            album_name = album_data.get("name", "")
            images = album_data.get("images", [])
            thumbnail_url = images[0]["url"] if images else ""

            track = Track(
                title=title,
                artist=artist,
                album=album_name,
                duration=duration,
                source="spotify",
                source_url=f"https://open.spotify.com/track/{item.get('id', '')}",
                source_id=item.get("id", ""),
                thumbnail_url=thumbnail_url,
            )
            tracks.append(track)

        return tracks

    def export_metadata(self, playlist: Playlist, output_file: Path) -> None:
        """Export playlist metadata to a JSON file."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        data = playlist.to_dict()
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print_success(f"Metadata exported to: {output_file}")

    def export_to_csv(self, playlist: Playlist, output_file: Path) -> None:
        """Export playlist to a CSV file."""
        import csv

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Artist", "Album", "Duration", "Track #", "Source"])
            for track in playlist.tracks:
                writer.writerow([
                    track.title,
                    track.artist,
                    track.album,
                    f"{int(track.duration // 60)}:{int(track.duration % 60):02d}",
                    track.track_number,
                    track.source,
                ])
        print_success(f"CSV exported to: {output_file}")
