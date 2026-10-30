use serde_json::{json, Value};
use std::{
    collections::HashMap,
    io::{BufRead, BufReader, Read, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tauri_plugin_opener::OpenerExt;

mod update_core;
mod update_http;
mod updates;

const MAX_FRAME: usize = 1024 * 1024;
const ENGINE_STOPPED: &str = "The voice engine stopped. Restart it to continue.";
static ENGINE_GENERATION: AtomicU64 = AtomicU64::new(1);
type Pending = HashMap<u64, mpsc::Sender<Result<Value, String>>>;

struct Engine {
    generation: u64,
    input: Mutex<Option<ChildStdin>>,
    child: Mutex<Option<Child>>,
    pending: Mutex<Pending>,
    serial: AtomicU64,
    closed: AtomicBool,
    failure: Mutex<Option<String>>,
    job: Mutex<isize>,
}

impl Engine {
    fn request(&self, method: &str, params: Value) -> Result<Value, String> {
        if self.closed.load(Ordering::Acquire) {
            return Err(self.failure_message());
        }
        let id = self.serial.fetch_add(1, Ordering::Relaxed);
        let bytes =
            serde_json::to_vec(&json!({"version":2,"id":id,"method":method,"params":params}))
                .map_err(|_| "Invalid command.")?;
        if bytes.len() + 1 > MAX_FRAME {
            return Err("This command is too large.".into());
        }
        let (sender, receiver) = mpsc::channel();
        {
            let mut pending = self.pending.lock().map_err(|_| "Engine unavailable.")?;
            if pending.len() >= 64 {
                return Err("The engine is busy. Please wait for the current operation.".into());
            }
            pending.insert(id, sender);
        }
        let sent = (|| -> Result<(), String> {
            let mut guard = self.input.lock().map_err(|_| "Engine unavailable.")?;
            let stream = guard.as_mut().ok_or("The voice engine stopped.")?;
            stream
                .write_all(&bytes)
                .and_then(|_| stream.write_all(b"\n"))
                .and_then(|_| stream.flush())
                .map_err(|_| "Cannot communicate with the voice engine.".into())
        })();
        if let Err(error) = sent {
            self.pending.lock().ok().map(|mut p| p.remove(&id));
            return Err(self
                .failure
                .lock()
                .ok()
                .and_then(|f| f.clone())
                .unwrap_or(error));
        }
        let response = receiver
            .recv_timeout(Duration::from_secs(30))
            .unwrap_or_else(|_| {
                Err("The engine did not respond. Check its status and try again.".into())
            });
        self.pending.lock().ok().map(|mut p| p.remove(&id));
        response
    }

    fn failure_message(&self) -> String {
        self.failure
            .lock()
            .ok()
            .and_then(|failure| failure.clone())
            .unwrap_or_else(|| ENGINE_STOPPED.into())
    }

    fn remember_failure(&self, event: &Value) {
        if event["event"] == "fatal" {
            if let Some(message) = event["payload"]["message"].as_str() {
                if !message.trim().is_empty() {
                    if let Ok(mut failure) = self.failure.lock() {
                        *failure = Some(message.chars().take(1024).collect());
                    }
                }
            }
        }
    }

    fn disconnect(&self) {
        self.closed.store(true, Ordering::Release);
        let message = self.failure_message();
        if let Ok(mut pending) = self.pending.lock() {
            for (_, sender) in pending.drain() {
                let _ = sender.send(Err(message.clone()));
            }
        }
    }

    fn shutdown(&self) {
        if !self.closed.load(Ordering::Acquire) {
            // A stalled request writer must not prevent process containment
            // from enforcing shutdown. Killing the child unblocks its pipe.
            if let Ok(mut input) = self.input.try_lock() {
                if let Some(mut stream) = input.take() {
                    thread::spawn(move || {
                        let _ = stream.write_all(
                            b"{\"version\":2,\"id\":0,\"method\":\"shutdown\",\"params\":{}}\n",
                        );
                        let _ = stream.flush();
                    });
                }
            }
        }
        if let Ok(mut child) = self.child.lock() {
            if let Some(child) = child.as_mut() {
                #[cfg(windows)]
                unsafe {
                    use windows_sys::Win32::{
                        Foundation::CloseHandle,
                        System::Threading::{OpenEventW, SetEvent},
                    };
                    let name: Vec<u16> = format!("Local\\VoicePrompt.Exit.{}\0", child.id())
                        .encode_utf16()
                        .collect();
                    let event = OpenEventW(0x0002, 0, name.as_ptr());
                    if !event.is_null() {
                        SetEvent(event);
                        CloseHandle(event);
                    }
                }
                for _ in 0..30 {
                    if child.try_wait().ok().flatten().is_some() {
                        break;
                    }
                    thread::sleep(Duration::from_millis(100));
                }
                let _ = child.kill();
                let _ = child.wait();
            }
        }
        self.disconnect();
        #[cfg(windows)]
        if let Ok(mut job) = self.job.lock() {
            if *job != 0 {
                unsafe {
                    windows_sys::Win32::Foundation::CloseHandle(*job as _);
                }
                *job = 0;
            }
        }
    }
}

struct DesktopState {
    restart_lock: tauri::async_runtime::Mutex<()>,
    engine: Mutex<Option<Arc<Engine>>>,
    launch_error: Mutex<Option<String>>,
    quitting: AtomicBool,
    anchor: Mutex<Option<(f64, f64)>>,
    previous_focus: Mutex<isize>,
}

fn engine(state: &DesktopState) -> Result<Arc<Engine>, String> {
    state
        .engine
        .lock()
        .map_err(|_| "Engine unavailable.".to_string())?
        .clone()
        .ok_or_else(|| {
            state
                .launch_error
                .lock()
                .ok()
                .and_then(|error| error.clone())
                .unwrap_or_else(|| "The voice engine is starting. Please wait.".into())
        })
}

#[cfg(windows)]
fn contain_process(child: &Child) -> Result<isize, String> {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::{Foundation::CloseHandle, System::JobObjects::*};
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return Err("Cannot create the engine process container.".into());
        }
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as _,
            std::mem::size_of_val(&limits) as u32,
        ) == 0
            || AssignProcessToJobObject(job, child.as_raw_handle() as _) == 0
        {
            CloseHandle(job);
            return Err("Cannot isolate the engine process tree.".into());
        }
        Ok(job as isize)
    }
}

fn spawn_engine(app: &AppHandle) -> Result<Arc<Engine>, String> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let smoke = arguments.first().is_some_and(|a| a == "--smoke-test");
    let mut command;
    if cfg!(debug_assertions) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|p| p.parent())
            .ok_or("Source directory is unavailable.")?;
        let python311 = root.join(".venv311/Scripts/python.exe");
        let python = if python311.is_file() {
            python311
        } else {
            root.join(".venv/Scripts/python.exe")
        };
        command = Command::new(if python.is_file() {
            python
        } else {
            "python".into()
        });
        command.current_dir(root).args([
            "-u",
            "-m",
            if smoke {
                "voiceprompt.engine_entry"
            } else {
                "voiceprompt.desktop_sidecar"
            },
        ]);
        if smoke {
            command.args(&arguments);
        }
    } else {
        let executable = app
            .path()
            .resource_dir()
            .map_err(|_| "Application resources are unavailable.")?
            .join("engine/VoicePromptEngine.exe");
        command = Command::new(executable);
        if smoke {
            command.args(&arguments);
        } else {
            command.arg("--desktop-sidecar");
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    if let Ok(path) = std::env::current_exe() {
        command.env("VOICEPROMPT_DESKTOP_EXE", path);
    }
    command.env("VOICEPROMPT_DESKTOP_PID", std::process::id().to_string());
    let mut child = command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().map_err(|_| "Cannot launch the voice engine. Reinstall the complete app, or check the source Python environment.".to_string())?;
    #[cfg(windows)]
    let job = match contain_process(&child) {
        Ok(job) => job,
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    #[cfg(not(windows))]
    let job = 0;
    let input = child.stdin.take();
    let output = child.stdout.take().ok_or("Engine output is unavailable.")?;
    // Always drain stderr. Provider diagnostics are not forwarded into the UI,
    // persisted or uploaded; they could contain user data or provider details.
    if let Some(mut stderr) = child.stderr.take() {
        thread::spawn(move || {
            let mut buffer = [0u8; 4096];
            while stderr.read(&mut buffer).unwrap_or(0) > 0 {}
        });
    }
    let engine = Arc::new(Engine {
        generation: ENGINE_GENERATION.fetch_add(1, Ordering::Relaxed),
        input: Mutex::new(input),
        child: Mutex::new(Some(child)),
        pending: Mutex::new(HashMap::new()),
        serial: AtomicU64::new(1),
        closed: AtomicBool::new(false),
        failure: Mutex::new(None),
        job: Mutex::new(job),
    });
    let reader_engine = engine.clone();
    let app = app.clone();
    thread::spawn(move || {
        let mut reader = BufReader::new(output);
        loop {
            let mut frame = Vec::new();
            // take() bounds allocation even for a faulty child's missing newline.
            let result = reader
                .by_ref()
                .take((MAX_FRAME + 1) as u64)
                .read_until(b'\n', &mut frame);
            if !matches!(result, Ok(n) if n > 0) || frame.len() > MAX_FRAME {
                break;
            }
            let Ok(mut value) = serde_json::from_slice::<Value>(&frame) else {
                break;
            };
            // Keep startup failures even when the WebView has not subscribed yet.
            // EOF and pending bootstrap requests must report the same cause.
            reader_engine.remember_failure(&value);
            if let Some(id) = value.get("id").and_then(Value::as_u64) {
                if let Some(sender) = reader_engine
                    .pending
                    .lock()
                    .ok()
                    .and_then(|mut pending| pending.remove(&id))
                {
                    let response = if value["ok"] == true {
                        Ok(value["result"].clone())
                    } else {
                        Err(value["error"]["message"]
                            .as_str()
                            .unwrap_or("The operation failed.")
                            .to_string())
                    };
                    let _ = sender.send(response);
                }
            } else {
                value["engineGeneration"] = json!(reader_engine.generation);
                let _ = app.emit("engine-event", &value);
            }
        }
        reader_engine.disconnect();
        let _ = app.emit("engine-disconnected", json!({"generation":reader_engine.generation,"message":reader_engine.failure_message()}));
        if smoke {
            let code = reader_engine
                .child
                .lock()
                .ok()
                .and_then(|mut child| child.as_mut().and_then(|child| child.wait().ok()))
                .and_then(|status| status.code())
                .unwrap_or(1);
            app.exit(code);
        }
    });
    Ok(engine)
}

#[tauri::command]
async fn engine_request(
    method: String,
    params: Value,
    state: State<'_, DesktopState>,
) -> Result<Value, String> {
    if method == "shutdown" || method.starts_with("update.") {
        return Err("Use the app's Quit action.".into());
    }
    let engine = engine(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let mut result = engine.request(&method, params)?;
        if method == "bootstrap" {
            result["engineGeneration"] = json!(engine.generation);
        }
        Ok(result)
    })
    .await
    .map_err(|_| "The operation was interrupted.".to_string())?
}

#[tauri::command]
async fn restart_engine(app: AppHandle, state: State<'_, DesktopState>) -> Result<(), String> {
    let _restart = state.restart_lock.lock().await;
    if app
        .state::<updates::Updates>()
        .installing
        .load(Ordering::Acquire)
    {
        return Err("VoicePrompt is closing to install an update.".into());
    }
    if state.quitting.load(Ordering::Acquire) {
        return Err("The app is closing.".into());
    }
    let old = {
        state
            .engine
            .lock()
            .map_err(|_| "Engine unavailable.")?
            .take()
    };
    if let Some(old) = old {
        tauri::async_runtime::spawn_blocking(move || old.shutdown())
            .await
            .map_err(|_| "Engine shutdown failed.")?;
    }
    *state
        .launch_error
        .lock()
        .map_err(|_| "Engine unavailable.")? = None;
    let replacement = spawn_engine(&app).inspect_err(|error| {
        if let Ok(mut failure) = state.launch_error.lock() {
            *failure = Some(error.clone());
        }
    })?;
    let generation = replacement.generation;
    *state.engine.lock().map_err(|_| "Engine unavailable.")? = Some(replacement);
    app.emit("engine-restarted", generation)
        .map_err(|_| "Cannot reconnect the interface.".to_string())
}

#[tauri::command]
fn window_action(window: WebviewWindow, action: &str) -> Result<(), String> {
    if window.label() != "main" {
        return Err("This action requires the main window.".into());
    }
    match action {
        "minimize" => window.minimize(),
        "maximize" => {
            if window.is_maximized().unwrap_or(false) {
                window.unmaximize()
            } else {
                window.maximize()
            }
        }
        "close" => window.hide(),
        _ => return Err("Unsupported window action.".into()),
    }
    .map_err(|_| "Cannot update the window.".into())
}

#[tauri::command]
fn open_main(app: AppHandle, page: Option<String>) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or("Main window unavailable.")?;
    main.show().map_err(|_| "Cannot open the app.")?;
    let _ = main.set_focus();
    if let Some(page) = page {
        let _ = app.emit_to("main", "navigate", json!({"page":page}));
    }
    Ok(())
}

fn allowed_url(text: &str) -> bool {
    let Ok(url) = url::Url::parse(text) else {
        return false;
    };
    if url.scheme() != "https"
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port().is_some()
    {
        return false;
    }
    match url.host_str().unwrap_or("") {
        "codeforces.com" | "www.codeforces.com" | "leetcode.com" | "www.leetcode.com"
        | "codechef.com" | "www.codechef.com" | "atcoder.jp" | "www.atcoder.jp" => true,
        "github.com" => url.path().starts_with("/MD-SOHAIL-AI/voiceprompt/releases"),
        _ => false,
    }
}

#[tauri::command]
fn open_link(app: AppHandle, url: String) -> Result<(), String> {
    if !allowed_url(&url) {
        return Err("Only verified contest and VoicePrompt release links can be opened.".into());
    }
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|_| "Cannot open your browser.".into())
}

#[tauri::command]
fn island_view(
    app: AppHandle,
    mode: &str,
    focus: bool,
    state: State<'_, DesktopState>,
) -> Result<(), String> {
    let window = app
        .get_webview_window("overlay")
        .ok_or("Island unavailable.")?;
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetForegroundWindow, IsWindow, SetForegroundWindow,
        };
        let own = window.hwnd().map(|handle| handle.0 as isize).unwrap_or(0);
        let foreground_before = GetForegroundWindow() as isize;
        if foreground_before != 0 && foreground_before != own {
            if let Ok(mut saved) = state.previous_focus.lock() {
                *saved = foreground_before;
            }
        }
        if mode != "expanded" && foreground_before == own {
            let previous = state.previous_focus.lock().map(|saved| *saved).unwrap_or(0);
            if previous != 0 && previous != own && IsWindow(previous as _) != 0 {
                if SetForegroundWindow(previous as _) == 0 {
                    let _ = window.hide();
                }
            } else {
                // Hiding the active window lets Windows restore the previous app.
                // show() below uses the nonactivating compact/peek style.
                let _ = window.hide();
            }
        }
    }
    if mode == "hidden" {
        return window.hide().map_err(|_| "Cannot hide the island.".into());
    }
    let (width, height): (f64, f64) = match mode {
        "compact" => (112.0, 32.0),
        "peek" => (280.0, 96.0),
        "expanded" => (320.0, 400.0),
        _ => return Err("Unsupported island view.".into()),
    };
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten())
        .ok_or("Display information unavailable.")?;
    let scale = monitor.scale_factor();
    let area = monitor.work_area();
    let left = area.position.x as f64 / scale;
    let top = area.position.y as f64 / scale;
    let right = left + area.size.width as f64 / scale;
    let bottom = top + area.size.height as f64 / scale;
    let height = height.min((bottom - top - 24.0).max(96.0));
    let mut anchor = state
        .anchor
        .lock()
        .map_err(|_| "Island position unavailable.")?;
    let (cx, base) = *anchor.get_or_insert(((left + right) / 2.0, bottom - 16.0));
    let x = (cx - width / 2.0).clamp(left + 8.0, (right - width - 8.0).max(left + 8.0));
    let y = (base - height).clamp(top + 8.0, (bottom - height - 8.0).max(top + 8.0));
    let _ = window.set_focusable(focus && mode == "expanded");
    window
        .set_size(tauri::LogicalSize::new(width, height))
        .map_err(|_| "Cannot resize the island.")?;
    window
        .set_position(tauri::LogicalPosition::new(x, y))
        .map_err(|_| "Cannot move the island.")?;
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::Graphics::Gdi::{CreateRoundRectRgn, SetWindowRgn};
        if let Ok(hwnd) = window.hwnd() {
            let radius = if mode == "compact" { 32.0 } else { 24.0 } * scale;
            let region = CreateRoundRectRgn(
                0,
                0,
                (width * scale).ceil() as i32 + 1,
                (height * scale).ceil() as i32 + 1,
                radius as i32,
                radius as i32,
            );
            if !region.is_null() {
                SetWindowRgn(hwnd.0 as _, region, 1);
            }
        }
    }
    window.show().map_err(|_| "Cannot show the island.")?;
    if focus && mode == "expanded" {
        let _ = window.set_focus();
    }
    #[cfg(windows)]
    if mode != "expanded" {
        let own = window.hwnd().map(|handle| handle.0 as isize).unwrap_or(0);
        let previous = state.previous_focus.lock().map(|saved| *saved).unwrap_or(0);
        let main = app
            .get_webview_window("main")
            .filter(|main| main.is_visible().unwrap_or(false));
        let fallback = main
            .and_then(|main| main.hwnd().ok())
            .map(|handle| handle.0 as isize)
            .unwrap_or(0);
        window
            .run_on_main_thread(move || unsafe {
                use windows_sys::Win32::UI::{
                    Input::KeyboardAndMouse::{GetFocus, SetFocus},
                    WindowsAndMessaging::{
                        GetForegroundWindow, GetShellWindow, IsChild, IsWindow, SetForegroundWindow,
                    },
                };
                // A WebView can reactivate its frame during show/resize. Restore
                // the destination after those operations as well as before them.
                if GetForegroundWindow() as isize == own {
                    let target = if previous != 0 && previous != own && IsWindow(previous as _) != 0
                    {
                        previous
                    } else if fallback != 0 {
                        fallback
                    } else {
                        GetShellWindow() as isize
                    };
                    if target != 0 && target != own {
                        SetForegroundWindow(target as _);
                    }
                }
                let focused = GetFocus();
                if own != 0 && (focused as isize == own || IsChild(own as _, focused) != 0) {
                    SetFocus(std::ptr::null_mut());
                }
            })
            .map_err(|_| "Cannot release the island keyboard focus.".to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn island_status(app: AppHandle) -> Result<Value, String> {
    let window = app
        .get_webview_window("overlay")
        .ok_or("Island unavailable.")?;
    let reported = window.is_focused().unwrap_or(false);
    let visible = window.is_visible().unwrap_or(false);
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetForegroundWindow, GetGUIThreadInfo, GetWindowLongPtrW, IsChild, GUITHREADINFO,
            GWL_EXSTYLE, WS_EX_NOACTIVATE,
        };
        let own = window
            .hwnd()
            .map_err(|_| "Island unavailable.".to_string())?
            .0 as _;
        let mut info: GUITHREADINFO = std::mem::zeroed();
        info.cbSize = std::mem::size_of_val(&info) as u32;
        let gui_available = GetGUIThreadInfo(0, &mut info) != 0;
        Ok(
            json!({"visible":visible, "reportedFocused":reported, "foreground":GetForegroundWindow() == own,
            "keyboardFocus":gui_available && (info.hwndFocus == own || IsChild(own, info.hwndFocus) != 0),
            "nonActivating":GetWindowLongPtrW(own, GWL_EXSTYLE) & WS_EX_NOACTIVATE as isize != 0,
            "guiAvailable":gui_available}),
        )
    }
    #[cfg(not(windows))]
    Ok(
        json!({"visible":visible, "reportedFocused":reported, "foreground":reported, "keyboardFocus":reported, "nonActivating":!reported}),
    )
}

#[tauri::command]
fn restore_island(x: f64, y: f64, state: State<'_, DesktopState>) -> Result<(), String> {
    if x.is_finite() && y.is_finite() && !(x == -1.0 && y == -1.0) {
        *state
            .anchor
            .lock()
            .map_err(|_| "Island position unavailable.")? = Some((x + 56.0, y + 32.0));
    }
    Ok(())
}

#[tauri::command]
fn remember_island(x: f64, y: f64, state: State<'_, DesktopState>) -> Result<(), String> {
    if !x.is_finite() || !y.is_finite() {
        return Err("Invalid island position.".into());
    }
    *state
        .anchor
        .lock()
        .map_err(|_| "Island position unavailable.")? = Some((x + 56.0, y + 32.0));
    let engine = engine(&state)?;
    thread::spawn(move || {
        let _ = engine.request(
            "island.position",
            json!({"x":x.round() as i32,"y":y.round() as i32}),
        );
    });
    Ok(())
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

pub fn run() {
    if updates::helper_mode() {
        return;
    }
    let smoke = std::env::args().any(|arg| arg == "--smoke-test");
    let mut context = tauri::generate_context!();
    let acceptance = std::env::var_os("VOICEPROMPT_ACCEPTANCE_DIR")
        .map(std::path::PathBuf::from)
        .filter(|path| path.is_absolute());
    if let Some(profile) = &acceptance {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        profile.hash(&mut hasher);
        context.config_mut().identifier =
            format!("app.voiceprompt.acceptance.a{:x}", hasher.finish());
    }
    for window in &mut context.config_mut().app.windows {
        window.devtools = Some(false);
        if let Some(profile) = &acceptance {
            window.data_directory = Some(profile.join("webview"));
            if let Ok(port) = std::env::var("VOICEPROMPT_INSPECT_PORT")
                .unwrap_or_default()
                .parse::<u16>()
            {
                if port >= 1024 {
                    window.devtools = Some(true);
                    window.additional_browser_args = Some(format!(
                        "--remote-debugging-port={port} --remote-debugging-address=127.0.0.1"
                    ));
                }
            }
        }
    }
    let mut builder = tauri::Builder::default()
        .manage(updates::Updates::new())
        .manage(DesktopState {
            restart_lock: tauri::async_runtime::Mutex::new(()),
            engine: Mutex::new(None),
            launch_error: Mutex::new(None),
            quitting: AtomicBool::new(false),
            anchor: Mutex::new(None),
            previous_focus: Mutex::new(0),
        })
        .plugin(tauri_plugin_opener::init());
    if !smoke {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
            let _ = open_main(app.clone(), None);
        }));
    }
    let app = builder
        .setup(move |app| {
            if !smoke {
                updates::schedule(app.handle().clone());
            }
            if smoke {
                if let Some(main) = app.get_webview_window("main") {
                    let _ = main.hide();
                }
            }
            use tauri::{
                menu::{Menu, MenuItem},
                tray::TrayIconBuilder,
            };
            let open = MenuItem::with_id(app, "open", "Open VoicePrompt", true, None::<&str>)?;
            let focus = MenuItem::with_id(app, "focus", "Tasks and timers", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit VoicePrompt", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &focus, &quit])?;
            let mut tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("VoicePrompt · Local dictation and daily focus");
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.on_menu_event(|app, event| match event.id.as_ref() {
                "open" => {
                    let _ = open_main(app.clone(), None);
                }
                "focus" => {
                    let _ = open_main(app.clone(), Some("Tasks".into()));
                }
                "quit" => app.exit(0),
                _ => (),
            })
            .build(app)?;
            let handle = app.handle().clone();
            match spawn_engine(&handle) {
                Ok(engine) => {
                    *app.state::<DesktopState>().engine.lock().unwrap() = Some(engine);
                }
                Err(error) => {
                    *app.state::<DesktopState>().launch_error.lock().unwrap() = Some(error);
                }
            }
            #[cfg(windows)]
            {
                let handle = handle.clone();
                thread::spawn(move || unsafe {
                    use windows_sys::Win32::{
                        Foundation::CloseHandle,
                        System::Threading::{CreateEventW, WaitForSingleObject},
                    };
                    let name: Vec<u16> =
                        format!("Local\\VoicePrompt.Exit.{}\0", std::process::id())
                            .encode_utf16()
                            .collect();
                    let event = CreateEventW(std::ptr::null(), 1, 0, name.as_ptr());
                    if !event.is_null() {
                        loop {
                            if WaitForSingleObject(event, 200) == 0 {
                                handle.exit(0);
                                break;
                            }
                            if handle
                                .state::<DesktopState>()
                                .quitting
                                .load(Ordering::Acquire)
                            {
                                break;
                            }
                        }
                        CloseHandle(event);
                    }
                });
            }
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
            engine_request,
            restart_engine,
            window_action,
            open_main,
            open_link,
            island_view,
            island_status,
            restore_island,
            remember_island,
            quit_app,
            updates::update_status,
            updates::update_check,
            updates::update_download,
            updates::update_cancel,
            updates::update_preferences,
            updates::update_install
        ])
        .build(context)
        .expect("Cannot initialize VoicePrompt desktop");
    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            let state = app.state::<DesktopState>();
            if !state.quitting.swap(true, Ordering::AcqRel) {
                api.prevent_exit();
                let engine = state.engine.lock().ok().and_then(|mut e| e.take());
                let app = app.clone();
                thread::spawn(move || {
                    if let Some(engine) = engine {
                        engine.shutdown();
                    }
                    app.exit(0);
                });
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn idle_engine() -> Engine {
        Engine {
            generation: 1,
            input: Mutex::new(None),
            child: Mutex::new(None),
            pending: Mutex::new(HashMap::new()),
            serial: AtomicU64::new(1),
            closed: AtomicBool::new(false),
            failure: Mutex::new(None),
            job: Mutex::new(0),
        }
    }

    #[test]
    fn startup_failure_survives_eof_and_late_bootstrap() {
        let engine = idle_engine();
        let message = "Another VoicePrompt instance is running. Quit it from the system tray, then select Restart engine.";
        engine.remember_failure(&json!({"event":"fatal","payload":{"message":message}}));
        engine.disconnect();
        assert_eq!(engine.request("bootstrap", json!({})), Err(message.into()));
        assert_eq!(engine.failure_message(), message);
    }

    #[test]
    fn pending_bootstrap_gets_specific_failure() {
        let engine = idle_engine();
        let (sender, receiver) = mpsc::channel();
        engine.pending.lock().unwrap().insert(1, sender);
        engine.remember_failure(&json!({"event":"fatal","payload":{"message":"Startup failed."}}));
        engine.disconnect();
        assert_eq!(receiver.recv().unwrap(), Err("Startup failed.".into()));
        assert!(engine.pending.lock().unwrap().is_empty());
    }

    #[test]
    fn unexpected_eof_keeps_restart_guidance() {
        let engine = idle_engine();
        engine.remember_failure(&json!({"event":"fatal","payload":{"message":""}}));
        engine.disconnect();
        assert_eq!(
            engine.request("bootstrap", json!({})),
            Err(ENGINE_STOPPED.into())
        );
    }

    #[test]
    fn links_are_restricted() {
        assert!(allowed_url("https://codeforces.com/contest/123"));
        assert!(!allowed_url("https://codeforces.com.evil.test/contest/123"));
        assert!(!allowed_url("https://user:pass@codeforces.com/"));
        assert!(!allowed_url("file:///C:/Windows/System32/cmd.exe"));
        assert!(!allowed_url("https://github.com/someone/else"));
    }

    #[test]
    fn shutdown_does_not_wait_for_a_stalled_request_writer() {
        let engine = Arc::new(idle_engine());
        let guard = engine.input.lock().unwrap();
        let copy = engine.clone();
        let (sender, receiver) = mpsc::channel();
        let worker = thread::spawn(move || {
            copy.shutdown();
            let _ = sender.send(());
        });
        let result = receiver.recv_timeout(Duration::from_secs(2));
        drop(guard);
        worker.join().unwrap();
        assert!(result.is_ok());
    }
}
