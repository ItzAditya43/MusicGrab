"""PyInstaller entry point: freezes into the `musicgrab-web` sidecar binary
that the Tauri desktop shell spawns."""

from musicgrab.webapp import run

if __name__ == "__main__":
    run()
