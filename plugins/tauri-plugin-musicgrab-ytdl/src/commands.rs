use tauri::{command, AppHandle, Runtime};

use crate::models::*;
use crate::Result;

#[cfg(mobile)]
use crate::MusicgrabYtdlExt;

#[command]
pub(crate) async fn search<R: Runtime>(
    app: AppHandle<R>,
    payload: SearchRequest,
) -> Result<SearchResponse> {
    #[cfg(mobile)]
    {
        app.musicgrab_ytdl().search(payload)
    }
    #[cfg(not(mobile))]
    {
        let _ = (app, payload);
        Err(crate::Error::UnsupportedPlatform)
    }
}

#[command]
pub(crate) async fn download<R: Runtime>(
    app: AppHandle<R>,
    payload: DownloadRequest,
) -> Result<DownloadResponse> {
    #[cfg(mobile)]
    {
        app.musicgrab_ytdl().download(payload)
    }
    #[cfg(not(mobile))]
    {
        let _ = (app, payload);
        Err(crate::Error::UnsupportedPlatform)
    }
}

#[command]
pub(crate) async fn list_downloads<R: Runtime>(app: AppHandle<R>) -> Result<ListDownloadsResponse> {
    #[cfg(mobile)]
    {
        app.musicgrab_ytdl().list_downloads(())
    }
    #[cfg(not(mobile))]
    {
        let _ = app;
        Err(crate::Error::UnsupportedPlatform)
    }
}
