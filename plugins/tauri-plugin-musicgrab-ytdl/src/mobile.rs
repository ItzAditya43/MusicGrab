use serde::de::DeserializeOwned;
use tauri::{
    plugin::{PluginApi, PluginHandle},
    AppHandle, Runtime,
};

use crate::models::*;
use crate::Result;

#[cfg(target_os = "android")]
const PLUGIN_IDENTIFIER: &str = "com.musicgrab.ytdl";

#[cfg(target_os = "android")]
pub fn init<R: Runtime, C: DeserializeOwned>(
    _app: &AppHandle<R>,
    api: PluginApi<R, C>,
) -> crate::Result<MusicgrabYtdl<R>> {
    let handle = api.register_android_plugin(PLUGIN_IDENTIFIER, "MusicgrabYtdlPlugin")?;
    Ok(MusicgrabYtdl(handle))
}

/// Handle to the Android-side plugin. Every call blocks on a JNI round trip
/// into Kotlin, which itself runs yt-dlp (via youtubedl-android) on a
/// background thread — so these should always be called from an async
/// command, never from the UI/main thread.
pub struct MusicgrabYtdl<R: Runtime>(PluginHandle<R>);

impl<R: Runtime> MusicgrabYtdl<R> {
    pub fn search(&self, payload: SearchRequest) -> Result<SearchResponse> {
        self.0
            .run_mobile_plugin("search", payload)
            .map_err(Into::into)
    }

    pub fn download(&self, payload: DownloadRequest) -> Result<DownloadResponse> {
        self.0
            .run_mobile_plugin("download", payload)
            .map_err(Into::into)
    }

    pub fn list_downloads(&self, payload: ()) -> Result<ListDownloadsResponse> {
        self.0
            .run_mobile_plugin("listDownloads", payload)
            .map_err(Into::into)
    }
}
