use std::{
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::Mutex,
    thread,
};
use tauri::{AppHandle, Emitter, Manager, State};

struct EngineState {
    process: Mutex<EngineProcess>,
}

struct EngineProcess {
    _child: Option<Child>,
    stdin: Option<ChildStdin>,
}

impl EngineProcess {
    fn send(&mut self, value: serde_json::Value) -> Result<(), String> {
        let stdin = self.stdin.as_mut().ok_or_else(|| "Voice engine is not running.".to_string())?;
        serde_json::to_writer(&mut *stdin, &value).map_err(|e| e.to_string())?;
        stdin.write_all(b"\n").map_err(|e| e.to_string())?;
        stdin.flush().map_err(|e| e.to_string())
    }
}

fn spawn_engine(app: &AppHandle) -> Result<EngineProcess, String> {
    let mut command = if cfg!(debug_assertions) {
        let mut cmd = Command::new("python");
        cmd.args(["-u", "-m", "voiceprompt.desktop_sidecar"]);
        cmd
    } else {
        let override_path = std::env::var_os("VOICEPROMPT_ENGINE").map(std::path::PathBuf::from);
        let exe = if let Some(path) = override_path {
            path
        } else {
            app.path()
                .resource_dir()
                .map_err(|e| e.to_string())?
                .join("bin")
                .join(if cfg!(windows) { "voiceprompt-engine.exe" } else { "voiceprompt-engine" })
        };
        Command::new(exe)
    };

    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Unable to start Voice Prompt engine: {e}"))?;

    let stdin = child.stdin.take().ok_or("Engine stdin unavailable.")?;
    let stdout = child.stdout.take().ok_or("Engine stdout unavailable.")?;
    let app_handle = app.clone();

    thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if line.len() > 256 * 1024 {
                continue;
            }
            match serde_json::from_str::<serde_json::Value>(&line) {
                Ok(event) => { let _ = app_handle.emit("engine-event", event); }
                Err(_) => { let _ = app_handle.emit("engine-event", serde_json::json!({"kind":"error","message":"Engine returned an invalid event."})); }
            }
        }
    });

    Ok(EngineProcess { _child: Some(child), stdin: Some(stdin) })
}

#[tauri::command]
fn apply_engine_profile(profile: serde_json::Value, engine: State<'_, EngineState>) -> Result<(), String> {
    engine.process.lock().map_err(|_| "Engine lock poisoned.".to_string())?
        .send(serde_json::json!({"command":"configure","profile":profile}))
}

#[tauri::command]
fn engine_start(engine: State<'_, EngineState>) -> Result<(), String> {
    engine.process.lock().map_err(|_| "Engine lock poisoned.".to_string())?
        .send(serde_json::json!({"command":"start"}))
}

#[tauri::command]
fn engine_stop(engine: State<'_, EngineState>) -> Result<(), String> {
    engine.process.lock().map_err(|_| "Engine lock poisoned.".to_string())?
        .send(serde_json::json!({"command":"stop"}))
}

#[tauri::command]
fn set_overlay_visible(app: AppHandle, visible: bool) -> Result<(), String> {
    let window = app.get_webview_window("overlay").ok_or("Overlay window unavailable.")?;
    if visible { window.show() } else { window.hide() }.map_err(|e| e.to_string())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let engine = spawn_engine(&app.handle()).map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
            app.manage(EngineState { process: Mutex::new(engine) });
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            apply_engine_profile,
            engine_start,
            engine_stop,
            set_overlay_visible,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Voice Prompt");
}
