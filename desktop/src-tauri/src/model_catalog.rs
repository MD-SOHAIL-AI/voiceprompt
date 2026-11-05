//! Only authenticated catalog data crosses into the speech engine.
use crate::update_core::{verify_payload, MAX_METADATA, PUBLIC_KEY};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    io::Read,
    path::PathBuf,
    sync::Mutex,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
static CATALOG_LOCK: Mutex<()> = Mutex::new(());

const FEED: &str = "https://github.com/MD-SOHAIL-AI/voiceprompt/releases/download/model-catalog/model-catalog.json";

#[derive(Serialize, Deserialize)]
pub struct Preferences {
    pub enabled: bool,
    pub last_checked: u64,
    pub message: String,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            enabled: true,
            last_checked: 0,
            message: String::new(),
        }
    }
}

fn directory() -> Result<PathBuf, String> {
    let root = std::env::var_os("VOICEPROMPT_ACCEPTANCE_DIR")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("LOCALAPPDATA").map(|p| PathBuf::from(p).join("VoicePrompt")))
        .ok_or("Model catalog storage is unavailable.")?;
    Ok(root.join("models/catalog"))
}

pub fn status() -> Preferences {
    directory()
        .ok()
        .and_then(|p| fs::read(p.join("preferences.json")).ok())
        .and_then(|v| serde_json::from_slice(&v).ok())
        .unwrap_or_default()
}

fn save(preferences: &Preferences) -> Result<(), String> {
    let directory = directory()?;
    fs::create_dir_all(&directory).map_err(|_| "Cannot save catalog preferences.")?;
    let path = directory.join("preferences.tmp");
    fs::write(
        &path,
        serde_json::to_vec(preferences).map_err(|_| "Invalid catalog preferences.")?,
    )
    .map_err(|_| "Cannot save catalog preferences.")?;
    fs::rename(path, directory.join("preferences.json"))
        .map_err(|_| "Cannot save catalog preferences.".into())
}

pub fn preferences(enabled: bool) -> Result<Value, String> {
    let _guard = CATALOG_LOCK
        .lock()
        .map_err(|_| "Catalog preferences unavailable.")?;
    let mut value = status();
    value.enabled = enabled;
    save(&value)?;
    serde_json::to_value(value).map_err(|_| "Invalid catalog preferences.".into())
}

pub fn verify(bytes: &[u8], key: &str) -> Result<Value, String> {
    let envelope = verify_payload(bytes, key)?;
    let value: Value =
        serde_json::from_str(&envelope.payload).map_err(|_| "The model catalog is unreadable.")?;
    if value["app"] != "VoicePrompt Models"
        || value["schema"] != 1
        || value["version"].as_u64().is_none()
        || !value["models"]
            .as_array()
            .is_some_and(|m| !m.is_empty() && m.len() <= 200)
    {
        return Err("This catalog is incompatible with VoicePrompt.".into());
    }
    Ok(value)
}

pub fn cached() -> Option<Value> {
    let path = directory().ok()?.join("signed.json");
    let mut bytes = Vec::new();
    fs::File::open(path)
        .ok()?
        .take(MAX_METADATA + 1)
        .read_to_end(&mut bytes)
        .ok()?;
    verify(&bytes, PUBLIC_KEY).ok()
}

pub fn refresh(
    manual: bool,
    apply: impl Fn(&Value) -> Result<(), String>,
) -> Result<Value, String> {
    let _guard = CATALOG_LOCK
        .lock()
        .map_err(|_| "Catalog refresh unavailable.")?;
    let mut preferences = status();
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    if !manual && (!preferences.enabled || now.saturating_sub(preferences.last_checked) < 86400) {
        return Ok(json!({"status": preferences, "catalog": cached()}));
    }
    if std::env::var_os("VOICEPROMPT_ACCEPTANCE_DIR").is_some() {
        return Ok(json!({"status": preferences, "catalog": cached()}));
    }
    let fetch = || -> Result<(Value, Vec<u8>), String> {
        let mut bytes = Vec::new();
        crate::update_http::get(FEED, Duration::from_secs(30))?
            .take(MAX_METADATA + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "Catalog download was interrupted.")?;
        let catalog = verify(&bytes, PUBLIC_KEY)?;
        if let Some(previous) = cached() {
            if catalog["version"].as_u64() < previous["version"].as_u64() {
                return Err(
                    "The downloaded catalog is older. Your existing catalog was kept.".into(),
                );
            }
        }
        apply(&catalog)?; // Preserve the last good signed cache if adapter validation fails.
        Ok((catalog, bytes))
    };
    preferences.last_checked = now;
    match fetch() {
        Ok((catalog, bytes)) => {
            let directory = directory()?;
            fs::create_dir_all(&directory).map_err(|_| "Cannot save the verified catalog.")?;
            fs::write(directory.join("signed.tmp"), bytes)
                .map_err(|_| "Cannot save the verified catalog.")?;
            fs::rename(directory.join("signed.tmp"), directory.join("signed.json"))
                .map_err(|_| "Cannot save the verified catalog.")?;
            preferences.message = "Model list updated. Downloads remain under your control.".into();
            save(&preferences)?;
            Ok(json!({"status": preferences, "catalog": catalog}))
        }
        Err(_) => {
            preferences.message = "The online catalog is unavailable. Your bundled or last verified model list is still available.".into();
            save(&preferences)?;
            Ok(json!({"status": preferences, "catalog": cached()}))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn refuses_unsigned_or_oversized_catalogs() {
        assert!(verify(
            br#"{"app":"VoicePrompt Models","schema":1,"version":1,"models":[{}]}"#,
            PUBLIC_KEY
        )
        .is_err());
        assert!(verify(&vec![0; MAX_METADATA as usize + 1], PUBLIC_KEY).is_err());
    }
}
