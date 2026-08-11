use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const SERVER_ADDR: &str = "127.0.0.1:8765";

struct SidecarHandle(Arc<Mutex<Option<CommandChild>>>);

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

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
                wait_for_server();
                let _ = window.show();
                let _ = window.set_focus();
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Kill the backend process when the app exits, rather than
            // leaving an orphaned server running on the user's machine.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(handle) = app_handle.try_state::<SidecarHandle>() {
                    if let Some(child) = handle.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
