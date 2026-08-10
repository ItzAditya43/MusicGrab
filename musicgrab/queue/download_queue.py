"""Download queue module for MusicGrab.

Manages a queue of tracks to download, with progress tracking and
concurrent download support.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from musicgrab.models.track import Track
from musicgrab.utils import (
    console,
    format_file_size,
    print_error,
    print_info,
    print_success,
    print_warning,
)


class DownloadStatus(Enum):
    """Status of a download item."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class QueueItem:
    """Represents an item in the download queue."""

    track: Track
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_path: Optional[Path] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "track": self.track.to_dict(),
            "status": self.status.value,
            "progress": self.progress,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "file_path": str(self.file_path) if self.file_path else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueueItem":
        """Create from dictionary."""
        return cls(
            track=Track.from_dict(data["track"]),
            status=DownloadStatus(data.get("status", "pending")),
            progress=data.get("progress", 0.0),
            error=data.get("error", ""),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            file_path=Path(data["file_path"]) if data.get("file_path") else None,
        )


class DownloadQueue:
    """Manages a queue of tracks for downloading."""

    def __init__(self, config) -> None:
        self.config = config
        self.items: List[QueueItem] = []
        self._lock = threading.Lock()
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

    def add(self, track: Track) -> QueueItem:
        """Add a track to the queue."""
        item = QueueItem(track=track)
        with self._lock:
            self.items.append(item)
        return item

    def add_many(self, tracks: List[Track]) -> List[QueueItem]:
        """Add multiple tracks to the queue."""
        items = []
        with self._lock:
            for track in tracks:
                item = QueueItem(track=track)
                self.items.append(item)
                items.append(item)
        return items

    def remove(self, index: int) -> bool:
        """Remove an item from the queue by index."""
        with self._lock:
            if 0 <= index < len(self.items):
                self.items.pop(index)
                return True
        return False

    def clear(self) -> None:
        """Clear all items from the queue."""
        with self._lock:
            self.items.clear()

    def get_pending(self) -> List[QueueItem]:
        """Get all pending items."""
        with self._lock:
            return [i for i in self.items if i.status == DownloadStatus.PENDING]

    def get_completed(self) -> List[QueueItem]:
        """Get all completed items."""
        with self._lock:
            return [i for i in self.items if i.status == DownloadStatus.COMPLETED]

    def get_failed(self) -> List[QueueItem]:
        """Get all failed items."""
        with self._lock:
            return [i for i in self.items if i.status == DownloadStatus.FAILED]

    @property
    def total_count(self) -> int:
        """Total number of items in the queue."""
        return len(self.items)

    @property
    def completed_count(self) -> int:
        """Number of completed items."""
        return len(self.get_completed())

    @property
    def failed_count(self) -> int:
        """Number of failed items."""
        return len(self.get_failed())

    @property
    def pending_count(self) -> int:
        """Number of pending items."""
        return len(self.get_pending())

    def set_callbacks(
        self,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ) -> None:
        """Set callback functions for progress, completion, and errors."""
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error

    def save(self, file_path: Path) -> None:
        """Save the queue state to a JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": [item.to_dict() for item in self.items],
            "saved_at": datetime.now().isoformat(),
        }
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print_info(f"Queue saved to: {file_path}")

    def load(self, file_path: Path) -> bool:
        """Load the queue state from a JSON file."""
        if not file_path.exists():
            return False
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            self.items = [QueueItem.from_dict(item) for item in data.get("items", [])]
            print_info(f"Queue loaded from: {file_path} ({len(self.items)} items)")
            return True
        except (json.JSONDecodeError, OSError) as e:
            print_error(f"Failed to load queue: {e}")
            return False

    def process(
        self,
        download_func: Callable,
        max_workers: int = 1,
    ) -> None:
        """Process the queue by downloading all pending items.

        Args:
            download_func: A function that takes a Track and returns a Path or None.
            max_workers: Maximum number of concurrent downloads.
        """
        pending = self.get_pending()
        total = len(pending)

        if total == 0:
            print_info("Queue is empty")
            return

        print_info(f"Processing {total} items in queue...")

        for i, item in enumerate(pending, 1):
            item.status = DownloadStatus.DOWNLOADING
            item.started_at = datetime.now()

            if self._on_progress:
                self._on_progress(item, i, total)

            try:
                result = download_func(item.track)
                if result:
                    item.status = DownloadStatus.COMPLETED
                    item.completed_at = datetime.now()
                    item.file_path = result
                    if self._on_complete:
                        self._on_complete(item, i, total)
                else:
                    item.status = DownloadStatus.FAILED
                    item.error = "Download failed"
                    if self._on_error:
                        self._on_error(item, i, total)
            except Exception as e:
                item.status = DownloadStatus.FAILED
                item.error = str(e)
                if self._on_error:
                    self._on_error(item, i, total)

        # Print summary
        completed = self.completed_count
        failed = self.failed_count
        console.print()
        if failed == 0:
            print_success(f"All {completed} tracks downloaded successfully!")
        else:
            print_warning(f"{completed} completed, {failed} failed out of {total}")

    def print_status(self) -> None:
        """Print the current queue status."""
        from musicgrab.utils import create_table, format_duration

        table = create_table("Download Queue", ["#", "Title", "Artist", "Status", "Progress"])

        for i, item in enumerate(self.items, 1):
            status_str = item.status.value.capitalize()
            progress_str = f"{item.progress:.0f}%" if item.progress > 0 else "-"
            table.add_row(
                str(i),
                item.track.title,
                item.track.artist,
                status_str,
                progress_str,
            )

        console.print(table)
