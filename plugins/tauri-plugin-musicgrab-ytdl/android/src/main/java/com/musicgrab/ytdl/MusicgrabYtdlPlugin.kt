package com.musicgrab.ytdl

import android.app.Activity
import android.media.MediaMetadataRetriever
import android.util.Base64
import android.util.Log
import android.webkit.WebView
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSArray
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

@InvokeArg
class SearchArgs {
    var query: String = ""
    var limit: Int = 15
}

@InvokeArg
class DownloadArgs {
    var url: String = ""
    var title: String? = null
    var artist: String? = null
    var audioFormat: String = "mp3"
}

@TauriPlugin
class MusicgrabYtdlPlugin(private val activity: Activity) : Plugin(activity) {
    private var initialized = false
    private var initError: String? = null

    override fun load(webView: WebView) {
        super.load(webView)
        try {
            YoutubeDL.getInstance().init(activity.applicationContext)
            FFmpeg.getInstance().init(activity.applicationContext)
            initialized = true
        } catch (e: Exception) {
            // Surfaced as an error on the first command instead of crashing
            // app startup — a failed yt-dlp/ffmpeg init shouldn't take down
            // the whole webview. Keep the real exception (class + message)
            // instead of a generic string — "failed to initialize" alone
            // gives no way to tell a missing-ABI native lib from a storage
            // permission problem from anything else.
            initialized = false
            initError = "${e.javaClass.simpleName}: ${e.message}"
            Log.e("MusicgrabYtdl", "yt-dlp/ffmpeg init failed", e)
        }
    }

    // Mirrors the desktop app's retry fix for the same class of bug: a
    // single yt-dlp/network hiccup used to be reported straight to the
    // user (as "search failed" or a hard download error) with no retry,
    // even though most such failures are transient (momentary YouTube
    // throttling) and a retry succeeds seconds later.
    private fun <T> retryYtdlp(attempts: Int = 3, block: () -> T): T {
        var lastError: Exception? = null
        for (attempt in 0 until attempts) {
            try {
                return block()
            } catch (e: Exception) {
                lastError = e
                Log.w("MusicgrabYtdl", "yt-dlp call failed (attempt ${attempt + 1}/$attempts)", e)
                if (attempt < attempts - 1) Thread.sleep(2000L * (attempt + 1))
            }
        }
        throw lastError!!
    }

    private fun downloadsDir(): File {
        val dir = File(activity.getExternalFilesDir(null), "MusicGrab")
        dir.mkdirs()
        return dir
    }

    // Downloads run with --embed-thumbnail, so cover art already lives
    // inside each file's own tags — no need for a separate metadata
    // store on top. Read it back as a data URI the webview can use
    // directly as an <img src>, same as the desktop app's artwork API.
    private fun extractArtwork(file: File): String? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            val art = retriever.embeddedPicture ?: return null
            val b64 = Base64.encodeToString(art, Base64.NO_WRAP)
            "data:image/jpeg;base64,$b64"
        } catch (e: Exception) {
            null
        } finally {
            retriever.release()
        }
    }

    @Command
    fun search(invoke: Invoke) {
        if (!initialized) {
            invoke.reject("yt-dlp/ffmpeg failed to initialize: ${initError ?: "unknown"}")
            return
        }
        val args = invoke.parseArgs(SearchArgs::class.java)
        Thread {
            try {
                val request = YoutubeDLRequest("ytsearch${args.limit}:${args.query}")
                request.addOption("--dump-json")
                request.addOption("--flat-playlist")
                request.addOption("--no-warnings")
                val response = retryYtdlp { YoutubeDL.getInstance().execute(request) }

                val results = JSArray()
                response.out.trim().lines().forEach { line ->
                    if (line.isBlank()) return@forEach
                    val json = JSONObject(line)
                    val item = JSObject()
                    item.put("id", json.optString("id"))
                    item.put("title", json.optString("title"))
                    item.put("uploader", json.optString("uploader", json.optString("channel", "")))
                    item.put("duration", json.optDouble("duration", 0.0))
                    item.put("thumbnail", json.optString("thumbnail", ""))
                    item.put(
                        "webpageUrl",
                        json.optString("webpage_url", "https://www.youtube.com/watch?v=${json.optString("id")}"),
                    )
                    results.put(item)
                }

                val ret = JSObject()
                ret.put("results", results)
                invoke.resolve(ret)
            } catch (e: Exception) {
                invoke.reject(e.message ?: "search failed")
            }
        }.start()
    }

    @Command
    fun download(invoke: Invoke) {
        if (!initialized) {
            invoke.reject("yt-dlp/ffmpeg failed to initialize: ${initError ?: "unknown"}")
            return
        }
        val args = invoke.parseArgs(DownloadArgs::class.java)
        Thread {
            try {
                val outDir = downloadsDir()
                val nameTemplate = if (args.artist != null && args.title != null) {
                    "${args.artist} - ${args.title}"
                } else {
                    "%(uploader)s - %(title)s"
                }

                val request = YoutubeDLRequest(args.url)
                request.addOption("-x")
                request.addOption("--audio-format", args.audioFormat)
                request.addOption("--embed-metadata")
                request.addOption("--embed-thumbnail")
                request.addOption("--no-warnings")
                request.addOption("-o", File(outDir, "$nameTemplate.%(ext)s").absolutePath)

                retryYtdlp { YoutubeDL.getInstance().execute(request, null) { _, _, _ -> } }

                val expected = outDir.listFiles { f -> f.nameWithoutExtension == nameTemplate }
                val file = expected?.firstOrNull()
                val ret = JSObject()
                ret.put("success", true)
                ret.put("path", file?.absolutePath)
                ret.put("thumbnail", file?.let { extractArtwork(it) })
                invoke.resolve(ret)
            } catch (e: Exception) {
                invoke.reject(e.message ?: "download failed")
            }
        }.start()
    }

    @Command
    fun listDownloads(invoke: Invoke) {
        try {
            val outDir = downloadsDir()
            val audioExtensions = setOf("mp3", "m4a", "flac", "wav", "ogg", "opus")
            val files = outDir.listFiles { f -> f.extension.lowercase() in audioExtensions } ?: emptyArray()

            val arr = JSArray()
            files.forEach { f ->
                val obj = JSObject()
                obj.put("name", f.nameWithoutExtension)
                obj.put("path", f.absolutePath)
                obj.put("size", f.length())
                obj.put("thumbnail", extractArtwork(f))
                arr.put(obj)
            }

            val ret = JSObject()
            ret.put("files", arr)
            invoke.resolve(ret)
        } catch (e: Exception) {
            invoke.reject(e.message ?: "list failed")
        }
    }
}
