const COMMANDS: &[&str] = &["search", "download", "list_downloads"];

fn main() {
    tauri_plugin::Builder::new(COMMANDS)
        .android_path("android")
        .build();
}
