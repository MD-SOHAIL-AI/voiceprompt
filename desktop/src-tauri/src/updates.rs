use crate::update_core::{self, Envelope, Manifest, FEED, MAX_METADATA, PUBLIC_KEY};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    pub phase: String,
    pub supported: bool,
    pub installed_version: String,
    pub version: Option<String>,
    pub notes: String,
    pub downloaded: u64,
    pub total: u64,
    pub last_checked: Option<u64>,
    pub automatic: bool,
    pub message: String,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Preferences {
    automatic: bool,
    last_checked: Option<u64>,
}

#[derive(Serialize, Deserialize)]
struct Job {
    parent_pid: u32,
    install_dir: PathBuf,
    envelope: Envelope,
}

pub struct Updates {
    status: Mutex<UpdateStatus>,
    preferences_write: Mutex<()>,
    busy: AtomicBool,
    last_attempt: AtomicU64,
    cancel: AtomicBool,
    pub installing: AtomicBool,
    directory: PathBuf,
}

fn read_bounded(path: &Path, limit: u64) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    fs::File::open(path)
        .map_err(|_| "Update information is unavailable.")?
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read update information.")?;
    if bytes.len() as u64 > limit {
        return Err("Update information exceeds its size limit.".into());
    }
    Ok(bytes)
}

fn write_json(path: &Path, value: &impl Serialize) -> Result<(), String> {
    let temporary = path.with_extension("tmp");
    let bytes = serde_json::to_vec(value).map_err(|_| "Cannot save update information.")?;
    let mut file = fs::File::create(&temporary)
        .map_err(|_| "Cannot save update information. Check free disk space.")?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| "Cannot save update information.")?;
    drop(file);
    fs::rename(&temporary, path).map_err(|_| "Cannot replace update information.".to_string())
}

fn update_directory() -> Result<PathBuf, String> {
    let root =
        std::env::var_os("LOCALAPPDATA").ok_or("Windows local application data is unavailable.")?;
    Ok(PathBuf::from(root).join("VoicePrompt").join("updates"))
}

fn cached_ready(directory: &Path, manifest: &Manifest) -> bool {
    directory.join("installer.exe").is_file()
        && read_bounded(&directory.join("download-complete.json"), 4096)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<serde_json::Value>(&bytes).ok())
            .is_some_and(|value| value["sha256"] == manifest.sha256)
}

fn installed() -> bool {
    !cfg!(debug_assertions)
        && std::env::var_os("VOICEPROMPT_ACCEPTANCE_DIR").is_none()
        && std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join("unins000.exe").is_file()))
            .unwrap_or(false)
}

impl Updates {
    pub fn new() -> Self {
        let directory = update_directory()
            .unwrap_or_else(|_| std::env::temp_dir().join("VoicePrompt-updates-unavailable"));
        let supported = installed() && update_core::key_data(PUBLIC_KEY).is_ok();
        let preferences = supported
            .then(|| read_bounded(&directory.join("preferences.json"), 4096).ok())
            .flatten()
            .and_then(|bytes| serde_json::from_slice::<Preferences>(&bytes).ok())
            .unwrap_or(Preferences {
                automatic: true,
                last_checked: None,
            });
        let mut status = UpdateStatus {
            phase: if supported { "idle" } else { "unavailable" }.into(),
            supported,
            installed_version: env!("CARGO_PKG_VERSION").into(),
            version: None,
            notes: String::new(),
            downloaded: 0,
            total: 0,
            automatic: preferences.automatic,
            last_checked: preferences.last_checked,
            message: if supported {
                String::new()
            } else {
                "Updates are available in the installed Windows app.".into()
            },
        };
        if supported {
            if let Ok(result) = read_bounded(&directory.join("result.json"), 8192) {
                if let Ok(result) = serde_json::from_slice::<serde_json::Value>(&result) {
                    status.message = result["message"]
                        .as_str()
                        .unwrap_or_default()
                        .chars()
                        .take(1024)
                        .collect();
                    if result["success"] == false {
                        status.phase = "error".into();
                    }
                }
                let _ = fs::remove_file(directory.join("result.json"));
            }
            if let Ok(bytes) = read_bounded(&directory.join("pending.json"), MAX_METADATA) {
                if let Ok((_, manifest)) = update_core::verify_envelope(&bytes, PUBLIC_KEY) {
                    if update_core::is_newer(&manifest.version, &status.installed_version)
                        .unwrap_or(false)
                    {
                        let ready = cached_ready(&directory, &manifest);
                        status.version = Some(manifest.version);
                        status.notes = manifest.notes;
                        status.total = manifest.size;
                        // Rehash only when the user downloads/restarts, off the UI thread.
                        status.phase = if ready { "ready" } else { "available" }.into();
                    } else {
                        let _ = fs::remove_file(directory.join("installer.exe"));
                        let _ = fs::remove_file(directory.join("pending.json"));
                        let _ = fs::remove_file(directory.join("download-complete.json"));
                    }
                }
            }
        }
        Self {
            directory,
            status: Mutex::new(status),
            preferences_write: Mutex::new(()),
            busy: AtomicBool::new(false),
            last_attempt: AtomicU64::new(0),
            cancel: AtomicBool::new(false),
            installing: AtomicBool::new(false),
        }
    }

    fn status(&self) -> UpdateStatus {
        self.status
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }

    fn change(&self, app: &AppHandle, change: impl FnOnce(&mut UpdateStatus)) {
        let snapshot = {
            let mut status = self.status.lock().unwrap_or_else(|e| e.into_inner());
            change(&mut status);
            status.clone()
        };
        let _ = app.emit("update-status", snapshot);
    }

    fn save_preferences(&self) -> Result<(), String> {
        let _write = self
            .preferences_write
            .lock()
            .map_err(|_| "Update preferences are unavailable.")?;
        let status = self.status();
        write_json(
            &self.directory.join("preferences.json"),
            &Preferences {
                automatic: status.automatic,
                last_checked: status.last_checked,
            },
        )
    }

    fn begin(&self) -> Result<(), String> {
        if self.installing.load(Ordering::Acquire) {
            return Err("VoicePrompt is closing to install an update.".into());
        }
        if !self.status().supported {
            return Err(self.status().message);
        }
        if self.busy.swap(true, Ordering::AcqRel) {
            return Err("An update operation is already running.".into());
        }
        self.cancel.store(false, Ordering::Release);
        if fs::create_dir_all(&self.directory).is_err() {
            self.busy.store(false, Ordering::Release);
            return Err(
                "Cannot create the update folder. Check free disk space and folder permissions."
                    .into(),
            );
        }
        Ok(())
    }

    fn metadata(&self) -> Result<(Envelope, Manifest), String> {
        update_core::verify_envelope(
            &read_bounded(&self.directory.join("pending.json"), MAX_METADATA)?,
            PUBLIC_KEY,
        )
    }

    fn check(&self, app: &AppHandle) -> Result<(), String> {
        let previous = self.status();
        self.begin()?;
        self.last_attempt.store(now(), Ordering::Release);
        self.change(app, |s| {
            s.phase = "checking".into();
            s.message.clear();
        });
        let result = (|| {
            let mut response = crate::update_http::get(FEED, Duration::from_secs(20))?;
            let mut bytes = Vec::new();
            response
                .by_ref()
                .take(MAX_METADATA + 1)
                .read_to_end(&mut bytes)
                .map_err(|_| "Could not read update information.")?;
            let (envelope, manifest) = update_core::verify_envelope(&bytes, PUBLIC_KEY)?;
            let newer = update_core::is_newer(&manifest.version, env!("CARGO_PKG_VERSION"))?;
            let already_downloaded = newer
                && previous.phase == "ready"
                && previous.version.as_deref() == Some(&manifest.version);
            if newer {
                write_json(&self.directory.join("pending.json"), &envelope)?;
            }
            self.change(app, |s| {
                s.phase = if already_downloaded {
                    "ready"
                } else if newer {
                    "available"
                } else {
                    "current"
                }
                .into();
                s.last_checked = Some(now());
                s.version = newer.then_some(manifest.version);
                s.notes = manifest.notes;
                s.total = manifest.size;
                s.message = if newer {
                    "A new version is available."
                } else {
                    "You're up to date."
                }
                .into();
            });
            self.save_preferences()
        })();
        self.finish(app, result)
    }

    fn finish(&self, app: &AppHandle, result: Result<(), String>) -> Result<(), String> {
        if let Err(error) = &result {
            self.change(app, |s| {
                s.phase = "error".into();
                s.message = error.clone();
            });
        }
        self.busy.store(false, Ordering::Release);
        result
    }

    fn download(&self, app: &AppHandle) -> Result<(), String> {
        self.begin()?;
        let result = (|| {
            let (_, manifest) = self.metadata()?;
            if !update_core::is_newer(&manifest.version, env!("CARGO_PKG_VERSION"))? {
                return Err("This version is already installed.".into());
            }
            self.change(app, |s| {
                s.phase = "downloading".into();
                s.message.clear();
                s.downloaded = 0;
            });
            let destination = self.directory.join("installer.exe");
            if destination.exists()
                && update_core::verify_installer(&destination, &manifest).is_ok()
            {
                write_json(
                    &self.directory.join("download-complete.json"),
                    &serde_json::json!({"sha256": manifest.sha256}),
                )?;
                self.change(app, |s| {
                    s.phase = "ready".into();
                    s.downloaded = s.total;
                });
                return Ok(());
            }
            available_space(
                &self.directory,
                manifest.size.saturating_mul(6) + 128 * 1024 * 1024,
            )?;
            let temporary = self.directory.join("installer.part");
            let mut file = fs::File::create(&temporary)
                .map_err(|_| "Cannot save the update. Check free disk space.")?;
            let mut response = crate::update_http::get(&manifest.url, Duration::from_secs(1800))?;
            if response
                .content_length()
                .is_some_and(|size| size != manifest.size)
            {
                return Err("The update download has an unexpected size.".into());
            }
            let mut last_event = Instant::now();
            let received = update_core::receive_download(
                &mut response,
                &mut file,
                manifest.size,
                || self.cancel.load(Ordering::Acquire),
                |received| {
                    if last_event.elapsed() >= Duration::from_millis(200) {
                        self.change(app, |s| s.downloaded = received);
                        last_event = Instant::now();
                    }
                },
            )?;
            let Some(received) = received else {
                drop(file);
                let _ = fs::remove_file(&temporary);
                self.change(app, |s| {
                    s.phase = "available".into();
                    s.message = "Download cancelled.".into();
                    s.downloaded = 0;
                });
                return Ok(());
            };
            file.sync_all()
                .map_err(|_| "Cannot finish saving the update.")?;
            drop(file);
            drop(update_core::verify_installer(&temporary, &manifest)?);
            fs::rename(&temporary, &destination)
                .map_err(|_| "Cannot stage the update. Close other installers and retry.")?;
            write_json(
                &self.directory.join("download-complete.json"),
                &serde_json::json!({"sha256": manifest.sha256}),
            )?;
            self.change(app, |s| {
                s.phase = "ready".into();
                s.downloaded = received;
                s.message = "Ready. Restart when it suits you.".into();
            });
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(self.directory.join("installer.part"));
        }
        self.finish(app, result)
    }
}

pub(crate) fn allowed_redirect(url: &url::Url) -> bool {
    url.scheme() == "https"
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
        && matches!(
            url.host_str(),
            Some(
                "github.com"
                    | "release-assets.githubusercontent.com"
                    | "objects.githubusercontent.com"
            )
        )
}

fn available_space(directory: &Path, needed: u64) -> Result<(), String> {
    #[cfg(windows)]
    unsafe {
        use std::os::windows::ffi::OsStrExt;
        let path: Vec<u16> = directory.as_os_str().encode_wide().chain(Some(0)).collect();
        let mut available = 0;
        if windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW(
            path.as_ptr(),
            &mut available,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        ) == 0
        {
            return Err("Cannot check free disk space for the update.".into());
        }
        if available < needed {
            return Err("There isn't enough free disk space. Free some space and retry.".into());
        }
    }
    Ok(())
}

fn main_window(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("Open the main window to manage updates.".into());
    }
    Ok(())
}

#[tauri::command]
pub fn update_status(
    window: WebviewWindow,
    state: State<'_, Updates>,
) -> Result<UpdateStatus, String> {
    main_window(&window)?;
    Ok(state.status())
}

#[tauri::command]
pub async fn update_check(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    main_window(&window)?;
    tauri::async_runtime::spawn_blocking(move || app.state::<Updates>().check(&app))
        .await
        .map_err(|_| "Update check was interrupted.".to_string())?
}

#[tauri::command]
pub async fn update_download(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    main_window(&window)?;
    tauri::async_runtime::spawn_blocking(move || app.state::<Updates>().download(&app))
        .await
        .map_err(|_| "Update download was interrupted.".to_string())?
}

#[tauri::command]
pub fn update_cancel(window: WebviewWindow, state: State<'_, Updates>) -> Result<(), String> {
    main_window(&window)?;
    state.cancel.store(true, Ordering::Release);
    Ok(())
}

#[tauri::command]
pub fn update_preferences(
    window: WebviewWindow,
    app: AppHandle,
    automatic: bool,
) -> Result<(), String> {
    main_window(&window)?;
    let state = app.state::<Updates>();
    if !state.status().supported {
        return Err(state.status().message);
    }
    fs::create_dir_all(&state.directory).map_err(|_| "Cannot save update preferences.")?;
    let old = state.status().automatic;
    state
        .status
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .automatic = automatic;
    if let Err(error) = state.save_preferences() {
        state
            .status
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .automatic = old;
        return Err(error);
    }
    state.change(&app, |_| {});
    Ok(())
}

pub fn schedule(app: AppHandle) {
    thread::spawn(move || {
        thread::sleep(Duration::from_secs(30));
        loop {
            let updates = app.state::<Updates>();
            let status = updates.status();
            if status.supported
                && status.automatic
                && !updates.busy.load(Ordering::Acquire)
                && now().saturating_sub(updates.last_attempt.load(Ordering::Acquire)) >= 6 * 3600
            {
                let _ = updates.check(&app);
            }
            thread::sleep(Duration::from_secs(60));
        }
    });
}

#[tauri::command]
pub async fn update_install(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    main_window(&window)?;
    let desktop = app.state::<crate::DesktopState>();
    let _restart = desktop.restart_lock.lock().await;
    let install_app = app.clone();
    tauri::async_runtime::spawn_blocking(move || install(&install_app))
        .await
        .map_err(|_| "Update installation was interrupted.".to_string())?
}

fn install(app: &AppHandle) -> Result<(), String> {
    let updates = app.state::<Updates>();
    if updates.status().phase != "ready" {
        return Err("Download and verify the update first.".into());
    }
    updates.begin()?;
    updates.installing.store(true, Ordering::Release);
    let mut verified_installer = false;
    let result = (|| {
        let (envelope, manifest) = updates.metadata()?;
        if !update_core::is_newer(&manifest.version, env!("CARGO_PKG_VERSION"))? {
            return Err("This version is already installed.".into());
        }
        let _verified =
            update_core::verify_installer(&updates.directory.join("installer.exe"), &manifest)?;
        verified_installer = true;
        let current = std::env::current_exe().map_err(|_| "Cannot locate the installed app.")?;
        let install_dir = current
            .parent()
            .ok_or("Cannot locate the installation folder.")?
            .to_path_buf();
        available_space(&install_dir, manifest.size.saturating_mul(6))?;
        let desktop = app.state::<crate::DesktopState>();
        let engine = crate::engine(&desktop)?;
        engine.request("update.prepare", serde_json::json!({}))?;
        let handoff = (|| {
            let helper = updates.directory.join("VoicePromptUpdater.exe");
            fs::copy(&current, &helper).map_err(|_| {
                "Cannot prepare the update helper. Close other installers and retry."
            })?;
            write_json(
                &updates.directory.join("job.json"),
                &Job {
                    parent_pid: std::process::id(),
                    install_dir,
                    envelope,
                },
            )?;
            let ready = updates.directory.join("helper-ready.json");
            let _ = fs::remove_file(&ready);
            let mut command = Command::new(helper);
            command
                .arg("--apply-update")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                command.creation_flags(0x08000000);
            }
            let mut child = command
                .spawn()
                .map_err(|_| "The update helper could not start.")?;
            let started = Instant::now();
            while started.elapsed() < Duration::from_secs(15) {
                if let Ok(bytes) = read_bounded(&ready, 4096) {
                    let value: serde_json::Value = serde_json::from_slice(&bytes)
                        .map_err(|_| "The update helper could not verify its handoff.")?;
                    if value["pid"] == child.id() {
                        return Ok(());
                    }
                }
                if child
                    .try_wait()
                    .map_err(|_| "Cannot check the update helper.")?
                    .is_some()
                {
                    return Err(
                        "The update helper exited before installation. Retry the download.".into(),
                    );
                }
                thread::sleep(Duration::from_millis(100));
            }
            let _ = child.kill();
            let _ = child.wait();
            Err("The update helper did not become ready. VoicePrompt is still running.".into())
        })();
        if let Err(error) = handoff {
            let _ = engine.request("update.cancel", serde_json::json!({}));
            return Err(error);
        }
        updates.installing.store(true, Ordering::Release);
        updates.change(app, |s| {
            s.phase = "installing".into();
            s.message = "Closing VoicePrompt to install the verified update…".into();
        });
        app.exit(0);
        Ok(())
    })();
    if result.is_err() {
        updates.installing.store(false, Ordering::Release);
    }
    let result = updates.finish(app, result);
    if verified_installer && result.is_err() {
        updates.change(app, |s| s.phase = "ready".into());
    }
    result
}

/// Runs before Tauri initialization, so single-instance handling cannot swallow
/// the helper and the installer can replace the original executable.
pub fn helper_mode() -> bool {
    let arguments: Vec<String> = std::env::args().collect();
    if arguments
        .get(1)
        .is_some_and(|value| value == "--verify-update")
    {
        let result = (|| {
            if arguments.len() != 4 {
                return Err("Expected metadata and installer paths.".to_string());
            }
            let (_, manifest) = update_core::verify_envelope(
                &read_bounded(Path::new(&arguments[2]), MAX_METADATA)?,
                PUBLIC_KEY,
            )?;
            drop(update_core::verify_installer(
                Path::new(&arguments[3]),
                &manifest,
            )?);
            Ok(())
        })();
        std::process::exit(if result.is_ok() { 0 } else { 1 });
    }
    if !std::env::args().any(|arg| arg == "--apply-update") {
        return false;
    }
    if let Err(error) = run_helper() {
        if let Ok(directory) = update_directory() {
            let _ = write_json(
                &directory.join("result.json"),
                &serde_json::json!({"success":false,"message":error}),
            );
        }
        #[cfg(windows)]
        unsafe {
            let text: Vec<u16> = format!("VoicePrompt could not finish updating. {error}\n\nRetry with the installer in your VoicePrompt updates folder, or download Setup from GitHub Releases. Your saved data is kept.\0").encode_utf16().collect();
            let title: Vec<u16> = "VoicePrompt update\0".encode_utf16().collect();
            windows_sys::Win32::UI::WindowsAndMessaging::MessageBoxW(
                std::ptr::null_mut(),
                text.as_ptr(),
                title.as_ptr(),
                0x10,
            );
        }
    }
    true
}

fn run_helper() -> Result<(), String> {
    let directory = update_directory()?;
    if std::env::current_exe()
        .map_err(|_| "Cannot locate updater.")?
        .canonicalize()
        .map_err(|_| "Cannot inspect updater.")?
        != directory
            .join("VoicePromptUpdater.exe")
            .canonicalize()
            .map_err(|_| "Cannot inspect updater location.")?
    {
        return Err("Unexpected updater location.".into());
    }
    let job: Job = serde_json::from_slice(&read_bounded(
        &directory.join("job.json"),
        MAX_METADATA + 4096,
    )?)
    .map_err(|_| "Invalid update handoff.")?;
    let (_, manifest) = update_core::verify_envelope(
        &serde_json::to_vec(&job.envelope).map_err(|_| "Invalid update handoff.")?,
        PUBLIC_KEY,
    )?;
    if !update_core::is_newer(&manifest.version, env!("CARGO_PKG_VERSION"))? {
        return Err("The update is not newer than the installed app.".into());
    }
    if !job.install_dir.is_absolute() || !job.install_dir.join("unins000.exe").is_file() {
        return Err("Cannot verify the installation folder.".into());
    }
    let _verified = update_core::verify_installer(&directory.join("installer.exe"), &manifest)?;
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::{
            Foundation::CloseHandle,
            System::Threading::{OpenProcess, QueryFullProcessImageNameW, WaitForSingleObject},
        };
        let process = OpenProcess(0x00100000 | 0x1000, 0, job.parent_pid); // SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        if process.is_null() {
            return Err("Cannot verify the running VoicePrompt process.".into());
        }
        let mut image = vec![0_u16; 32768];
        let mut length = image.len() as u32;
        let queried = QueryFullProcessImageNameW(process, 0, image.as_mut_ptr(), &mut length);
        let expected = job
            .install_dir
            .join("VoicePrompt.exe")
            .canonicalize()
            .map_err(|_| "Cannot locate the installed app.")?;
        let actual = PathBuf::from(String::from_utf16_lossy(&image[..length as usize]));
        if queried == 0 || actual.canonicalize().ok().as_ref() != Some(&expected) {
            CloseHandle(process);
            return Err("The running app does not match the installation folder.".into());
        }
        write_json(
            &directory.join("helper-ready.json"),
            &serde_json::json!({"pid":std::process::id()}),
        )?;
        let waited = WaitForSingleObject(process, 60000);
        CloseHandle(process);
        if waited != 0 {
            return Err("VoicePrompt did not close. Quit it from the tray and retry.".into());
        }
    }
    let status = Command::new(directory.join("installer.exe"))
        .args([
            "/SILENT",
            "/SP-",
            "/NORESTART",
            "/RESTARTEXITCODE=3010",
            "/VOICEPROMPTUPDATE=1",
        ])
        .arg(format!("/DIR={}", job.install_dir.display()))
        .arg(format!("/LOG={}", directory.join("install.log").display()))
        .status()
        .map_err(|_| "Windows could not start Setup. Retry the downloaded installer.")?;
    let success = status.success();
    let message = if status.code() == Some(3010) {
        "Setup needs a Windows restart to finish. Restart Windows when convenient; no restart was forced."
    } else if success {
        "VoicePrompt was updated successfully."
    } else {
        "Setup did not finish. Retry the downloaded installer or reinstall from GitHub Releases."
    };
    write_json(
        &directory.join("result.json"),
        &serde_json::json!({"success":success,"message":message,"exitCode":status.code()}),
    )?;
    if success {
        let installed: serde_json::Value = serde_json::from_slice(&read_bounded(
            &job.install_dir.join("build-manifest.json"),
            MAX_METADATA,
        )?)
        .map_err(|_| "Setup finished, but the installed build information could not be read.")?;
        if installed["engine_version"] != manifest.version {
            return Err("Setup finished, but the installed version did not match the update. Retry Setup from the updates folder.".into());
        }
        Command::new(job.install_dir.join("VoicePrompt.exe"))
            .spawn()
            .map_err(|_| {
                "Updated successfully, but VoicePrompt could not reopen. Open it from Start."
            })?;
    } else {
        return Err(message.into());
    }
    let _ = fs::remove_file(directory.join("job.json"));
    let _ = fs::remove_file(directory.join("helper-ready.json"));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn an_older_cached_installer_is_not_ready_for_a_new_release() {
        let directory =
            std::env::temp_dir().join(format!("voiceprompt-ready-{}", std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let (_, manifest) = update_core::verify_envelope(
            include_bytes!("../test-fixtures/update.json"),
            include_str!("../test-fixtures/update.pub"),
        )
        .unwrap();
        fs::write(directory.join("installer.exe"), b"abc").unwrap();
        assert!(!cached_ready(&directory, &manifest));
        write_json(
            &directory.join("download-complete.json"),
            &serde_json::json!({"sha256": "old-release"}),
        )
        .unwrap();
        assert!(!cached_ready(&directory, &manifest));
        write_json(
            &directory.join("download-complete.json"),
            &serde_json::json!({"sha256": manifest.sha256}),
        )
        .unwrap();
        assert!(cached_ready(&directory, &manifest));
        fs::remove_file(directory.join("installer.exe")).unwrap();
        fs::remove_file(directory.join("download-complete.json")).unwrap();
        fs::remove_dir(directory).unwrap();
    }
    #[test]
    fn redirects_must_stay_on_github_asset_hosts() {
        for address in [
            "http://github.com/x",
            "https://evil.example/x",
            "https://github.com.evil.example/x",
            "https://user@github.com/x",
            "https://github.com:444/x",
        ] {
            assert!(!allowed_redirect(&url::Url::parse(address).unwrap()));
        }
        assert!(allowed_redirect(
            &url::Url::parse("https://release-assets.githubusercontent.com/x").unwrap()
        ));
    }
}
