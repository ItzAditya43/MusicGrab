use tauri::WebviewUrl;

#[cfg(desktop)]
mod desktop {
    use std::net::TcpStream;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    use tauri::Manager;
    use tauri_plugin_shell::process::{CommandChild, CommandEvent};
    use tauri_plugin_shell::ShellExt;

    pub const SERVER_ADDR: &str = "127.0.0.1:8765";

    pub struct SidecarHandle(pub Arc<Mutex<Option<CommandChild>>>);

    fn wait_for_server() -> bool {
        for _ in 0..150 {
            // ~30s at 200ms steps
            if TcpStream::connect_timeout(
                &SERVER_ADDR.parse().expect("valid socket addr"),
                Duration::from_millis(200),
            )
            .is_ok()
            {
                return true;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        false
    }

    // Desktop only: spawn the Python backend as a sidecar and reveal the
    // window (created hidden in run()) once it's actually accepting
    // connections. Mobile has no sidecar process model — see run()'s
    // mobile branch, which instead loads a static "connect to your PC"
    // page bundled in the app.
    pub fn spawn_backend(app: &tauri::App) {
        let (mut rx, child) = app
            .shell()
            .sidecar("musicgrab-web")
            .expect("failed to resolve musicgrab-web sidecar")
            .spawn()
            .expect("failed to spawn musicgrab-web backend");

        app.manage(SidecarHandle(Arc::new(Mutex::new(Some(child)))));

        // Forward backend stdout/stderr to the app log instead of
        // discarding it, so download/server errors are visible in
        // `tauri dev` and the OS-level log on a packaged build.
        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        log::info!("[musicgrab-web] {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Stderr(line) => {
                        log::warn!("[musicgrab-web] {}", String::from_utf8_lossy(&line));
                    }
                    _ => {}
                }
            }
        });

        // Don't show a blank window while the backend is still booting;
        // poll until it accepts connections, then reveal it.
        let window = app
            .get_webview_window("main")
            .expect("main window must exist");
        std::thread::spawn(move || {
            // The webview starts loading SERVER_ADDR immediately on window
            // creation, racing the sidecar's startup — it can load a
            // "connection refused" page before the backend is actually
            // listening. Force a reload once the port is confirmed open,
            // then reveal the (now-correct) window.
            wait_for_server();
            let _ = window.eval("window.location.reload()");
            std::thread::sleep(Duration::from_millis(150));
            let _ = window.show();
            let _ = window.set_focus();
        });
    }

    pub fn kill_backend(app_handle: &tauri::AppHandle) {
        if let Some(handle) = app_handle.try_state::<SidecarHandle>() {
            if let Some(child) = handle.0.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Two independent WebKitGTK-on-Linux issues that both manifest as the
    // same symptom: a window that opens, shows its title bar, and then
    // stays permanently blank/transparent (the desktop behind it visibly
    // bleeds through) with no crash and no error anywhere:
    //
    // 1. The DMA-BUF renderer can simply fail to paint on some Wayland
    //    compositors. Falling back to the software/EGL path avoids it.
    // 2. WebKitGTK's bubblewrap sandbox puts the WebProcess in its own
    //    network namespace, which can (intermittently — this was
    //    observed to work on some launches and not others) fail to reach
    //    127.0.0.1, silently hanging the desktop app's local sidecar
    //    server navigation forever. Confirmed as the actual root cause
    //    by reproducing and fixing it live: WEBKIT_FORCE_SANDBOX=0 turned
    //    a reliably-blank window into a working one. The sidecar we talk
    //    to is our own spawned process on loopback only, so disabling
    //    the sandbox here isn't giving up any real isolation.
    //
    // Both must be set before the webview is created. No-op on
    // X11/Windows/macOS.
    #[cfg(all(desktop, target_os = "linux"))]
    {
        // SAFETY: called at process startup, single-threaded, before any
        // webview (and therefore any thread reading these vars) is created.
        unsafe {
            std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
            std::env::set_var("WEBKIT_FORCE_SANDBOX", "0");
        }
    }

    let mut builder = tauri::Builder::default();

    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_shell::init());
    }

    #[cfg(target_os = "android")]
    {
        builder = builder.plugin(tauri_plugin_musicgrab_ytdl::init());
    }

    builder = builder.setup(|app| {
        if cfg!(debug_assertions) {
            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .level(log::LevelFilter::Info)
                    .build(),
            )?;
        }

        // The window is built in code (not declared in tauri.conf.json) so
        // we can attach a permissive navigation handler — desktop only
        // ever talks to the sidecar it spawned on 127.0.0.1, so this is
        // not opening up anything that wasn't already local-only.
        #[cfg(desktop)]
        let url = WebviewUrl::External(format!("http://{}", desktop::SERVER_ADDR).parse().unwrap());
        // Android is a standalone app: it loads the real bundled frontend
        // (musicgrab/web, via tauri.android.conf.json's frontendDist) and
        // downloads on-device through the musicgrab-ytdl plugin instead of
        // talking to a spawned backend — see plugins/tauri-plugin-musicgrab-ytdl.
        #[cfg(target_os = "android")]
        let url = WebviewUrl::App("index.html".into());

        #[allow(unused_mut)] // only mutated further in the #[cfg(desktop)] block below
        let mut win_builder = tauri::WebviewWindowBuilder::new(app, "main", url)
            .title("MusicGrab")
            .on_navigation(|_url| true);

        #[cfg(desktop)]
        {
            win_builder = win_builder
                .inner_size(1280.0, 800.0)
                .min_inner_size(860.0, 560.0)
                .center()
                .visible(false); // shown by spawn_backend() once the sidecar is ready
        }

        win_builder.build()?;

        #[cfg(desktop)]
        desktop::spawn_backend(app);

        Ok(())
    });

    #[cfg(desktop)]
    {
        builder
            .build(tauri::generate_context!())
            .expect("error while building tauri application")
            .run(|app_handle, event| {
                // Kill the backend process when the app exits, rather than
                // leaving an orphaned server running on the user's machine.
                if let tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit = event {
                    desktop::kill_backend(app_handle);
                }
            });
    }

    #[cfg(not(desktop))]
    {
        builder
            .run(tauri::generate_context!())
            .expect("error while running tauri application");
    }
}
