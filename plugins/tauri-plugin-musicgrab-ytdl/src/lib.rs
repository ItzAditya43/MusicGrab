#[cfg(mobile)]
use tauri::Manager;
use tauri::{
    plugin::{Builder, TauriPlugin},
    Runtime,
};

mod commands;
mod error;
mod models;

#[cfg(mobile)]
mod mobile;

pub use error::{Error, Result};
pub use models::*;

#[cfg(mobile)]
use mobile::MusicgrabYtdl;

#[cfg(mobile)]
pub trait MusicgrabYtdlExt<R: Runtime> {
    fn musicgrab_ytdl(&self) -> &MusicgrabYtdl<R>;
}

#[cfg(mobile)]
impl<R: Runtime, T: Manager<R>> MusicgrabYtdlExt<R> for T {
    fn musicgrab_ytdl(&self) -> &MusicgrabYtdl<R> {
        self.state::<MusicgrabYtdl<R>>().inner()
    }
}

/// On-device YouTube downloading for the Android build, backed by
/// youtubedl-android (bundled Python + yt-dlp + ffmpeg). No-op / returns
/// UnsupportedPlatform on desktop, which spawns the real Python backend as
/// a sidecar instead — see src-tauri/src/lib.rs.
pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("musicgrab-ytdl")
        .invoke_handler(tauri::generate_handler![
            commands::search,
            commands::download,
            commands::list_downloads,
        ])
        .setup(|_app, _api| {
            #[cfg(mobile)]
            {
                let musicgrab_ytdl = mobile::init(_app, _api)?;
                _app.manage(musicgrab_ytdl);
            }
            Ok(())
        })
        .build()
}
