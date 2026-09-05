use tauri::Manager;

#[cfg(target_os = "linux")]
use webkit2gtk::{PermissionRequestExt, SettingsExt, WebViewExt};

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            #[cfg(target_os = "linux")]
            {
                let win = app.get_webview_window("main");
                eprintln!("[TAURI SETUP] get_webview_window('main'): found = {}", win.is_some());
                if let Some(window) = win {
                    let res = window.with_webview(|webview| {
                        let wv = webview.inner();
                        if let Some(settings) = wv.settings() {
                            settings.set_enable_media_stream(true);
                            settings.set_enable_webrtc(true);
                            settings.set_enable_webgl(true);
                            eprintln!("[TAURI SETUP] WebKit media-stream, webrtc, and webgl settings enabled");
                        } else {
                            eprintln!("[TAURI SETUP] WebKit wv.settings() was None");
                        }

                        wv.connect_permission_request(|_wv, req| {
                            eprintln!("[TAURI PERMISSION] Auto-allowing webview permission request");
                            req.allow();
                            true
                        });
                    });
                    eprintln!("[TAURI SETUP] with_webview dispatch result: {:?}", res);
                } else {
                    eprintln!("[TAURI SETUP] Warning: 'main' window not found during setup");
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
