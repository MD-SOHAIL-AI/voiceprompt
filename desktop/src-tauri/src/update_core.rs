//! The release tool, app and detached helper use the same trust and version rules.
use minisign_verify::{PublicKey, Signature};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Write},
    path::Path,
};
use url::Url;

pub const REPOSITORY: &str = "MD-SOHAIL-AI/voiceprompt";
pub const FEED: &str =
    "https://github.com/MD-SOHAIL-AI/voiceprompt/releases/latest/download/latest.json";
pub const MAX_METADATA: u64 = 128 * 1024;
pub const MAX_INSTALLER: u64 = 2 * 1024 * 1024 * 1024 - 1;
pub const PUBLIC_KEY: &str = include_str!("../update-public-key.pub");

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    pub payload: String,
    pub signature: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: u32,
    pub app: String,
    pub channel: String,
    pub target: String,
    pub version: String,
    pub notes: String,
    pub published_at: String,
    pub url: String,
    pub size: u64,
    pub sha256: String,
}

pub fn key_data(key: &str) -> Result<&str, String> {
    key.lines()
        .map(str::trim)
        .find(|line| !line.is_empty() && !line.starts_with("untrusted comment:"))
        .ok_or_else(|| "Update signing is not configured in this build.".into())
}

pub fn verify_envelope(bytes: &[u8], key: &str) -> Result<(Envelope, Manifest), String> {
    if bytes.len() as u64 > MAX_METADATA {
        return Err("Update information exceeds its size limit.".into());
    }
    let envelope: Envelope = serde_json::from_slice(bytes)
        .map_err(|_| "Update information is unreadable. Please try again later.")?;
    let key = PublicKey::from_base64(key_data(key)?)
        .map_err(|_| "The update verification key is invalid.")?;
    let signature = Signature::decode(&envelope.signature)
        .map_err(|_| "The update signature is unreadable.")?;
    key.verify(envelope.payload.as_bytes(), &signature, false)
        .map_err(|_| "Update verification failed. No installer will run.")?;
    let manifest: Manifest = serde_json::from_str(&envelope.payload)
        .map_err(|_| "The signed update information is unreadable.")?;
    validate_manifest(&manifest)?;
    Ok((envelope, manifest))
}

pub fn stable_version(version: &str) -> Result<semver::Version, String> {
    let parsed = semver::Version::parse(version).map_err(|_| "Invalid update version.")?;
    if !parsed.pre.is_empty() || !parsed.build.is_empty() {
        return Err("Only stable releases belong in the update feed.".into());
    }
    Ok(parsed)
}

pub fn is_newer(candidate: &str, installed: &str) -> Result<bool, String> {
    let installed = semver::Version::parse(installed).map_err(|_| "Invalid installed version.")?;
    Ok(stable_version(candidate)? > installed)
}

pub fn validate_manifest(manifest: &Manifest) -> Result<(), String> {
    if manifest.schema != 1
        || manifest.app != "app.voiceprompt.desktop"
        || manifest.channel != "stable"
        || manifest.target != "windows-x86_64"
    {
        return Err("This update is incompatible with this app.".into());
    }
    stable_version(&manifest.version)?;
    let url = Url::parse(&manifest.url).map_err(|_| "Invalid installer address.")?;
    let expected = format!(
        "/{REPOSITORY}/releases/download/v{}/VoicePrompt-Setup-{}-x64.exe",
        manifest.version, manifest.version
    );
    if url.scheme() != "https"
        || url.host_str() != Some("github.com")
        || url.path() != expected
        || url.port().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err("The installer address does not belong to this release.".into());
    }
    if manifest.size == 0
        || manifest.size > MAX_INSTALLER
        || manifest.sha256.len() != 64
        || !manifest
            .sha256
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || manifest.notes.len() > 48 * 1024
        || manifest.published_at.len() > 64
    {
        return Err("Invalid update size, checksum or release notes.".into());
    }
    Ok(())
}

pub fn verify_installer(path: &Path, manifest: &Manifest) -> Result<File, String> {
    // Keep this handle open through launch: Windows denies writes/deletes while
    // allowing the loader to read the verified executable.
    let mut options = std::fs::OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(1); // FILE_SHARE_READ
    }
    let mut file = options
        .open(path)
        .map_err(|_| "The downloaded installer is unavailable. Download it again.")?;
    if file
        .metadata()
        .map_err(|_| "Cannot inspect the installer.")?
        .len()
        != manifest.size
    {
        return Err("The installer is incomplete. Download it again.".into());
    }
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|_| "Cannot read the downloaded installer.")?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    if format!("{:x}", digest.finalize()) != manifest.sha256 {
        return Err("Installer verification failed. Download it again.".into());
    }
    Ok(file)
}

/// None means cancelled; only an exact, complete stream may become executable.
pub fn receive_download(
    reader: &mut impl Read,
    writer: &mut impl Write,
    expected: u64,
    cancelled: impl Fn() -> bool,
    mut progress: impl FnMut(u64),
) -> Result<Option<u64>, String> {
    let mut received = 0_u64;
    let mut buffer = [0; 64 * 1024];
    loop {
        if cancelled() {
            return Ok(None);
        }
        let count = reader
            .read(&mut buffer)
            .map_err(|_| "The download was interrupted. Retry to download again.")?;
        if cancelled() {
            return Ok(None);
        }
        if count == 0 {
            break;
        }
        received += count as u64;
        if received > expected {
            return Err("The update exceeded its expected size.".into());
        }
        writer
            .write_all(&buffer[..count])
            .map_err(|_| "Cannot save the update. Check free disk space.")?;
        progress(received);
    }
    if received != expected {
        return Err("The installer is incomplete. Download it again.".into());
    }
    Ok(Some(received))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn downloads_reject_truncation_oversize_interruption_and_cancellation() {
        use std::io::Cursor;
        let mut output = Vec::new();
        assert_eq!(
            receive_download(&mut Cursor::new(b"abc"), &mut output, 3, || false, |_| {}).unwrap(),
            Some(3)
        );
        assert_eq!(output, b"abc");
        let cancel = std::cell::Cell::new(false);
        let mut partial = Vec::new();
        assert_eq!(
            receive_download(
                &mut Cursor::new(vec![0; 128 * 1024]),
                &mut partial,
                128 * 1024,
                || cancel.get(),
                |_| cancel.set(true)
            )
            .unwrap(),
            None
        );
        assert_eq!(partial.len(), 64 * 1024);
        assert!(receive_download(
            &mut Cursor::new(b"ab"),
            &mut Vec::new(),
            3,
            || false,
            |_| {}
        )
        .is_err());
        assert!(receive_download(
            &mut Cursor::new(b"abcd"),
            &mut Vec::new(),
            3,
            || false,
            |_| {}
        )
        .is_err());
        assert_eq!(
            receive_download(
                &mut Cursor::new(b"abc"),
                &mut Vec::new(),
                3,
                || true,
                |_| {}
            )
            .unwrap(),
            None
        );
        struct Interrupted;
        impl Read for Interrupted {
            fn read(&mut self, _: &mut [u8]) -> std::io::Result<usize> {
                Err(std::io::Error::new(
                    std::io::ErrorKind::ConnectionReset,
                    "offline",
                ))
            }
        }
        assert!(receive_download(&mut Interrupted, &mut Vec::new(), 3, || false, |_| {}).is_err());
    }

    #[test]
    fn signed_metadata_roundtrip_rejects_tampering_and_other_keys() {
        let bytes = include_bytes!("../test-fixtures/update.json");
        let key = include_str!("../test-fixtures/update.pub");
        let (mut envelope, manifest) = verify_envelope(bytes, key).unwrap();
        assert_eq!(manifest.version, "0.6.2");
        assert!(verify_envelope(bytes, PUBLIC_KEY).is_err());
        envelope.payload = envelope.payload.replace("0.6.2", "9.0.0");
        assert!(verify_envelope(&serde_json::to_vec(&envelope).unwrap(), key).is_err());
    }

    pub fn manifest() -> Manifest {
        Manifest { schema: 1, app: "app.voiceprompt.desktop".into(), channel: "stable".into(), target: "windows-x86_64".into(), version: "0.6.2".into(), notes: "A release".into(), published_at: "2026-10-30T00:00:00Z".into(), url: "https://github.com/MD-SOHAIL-AI/voiceprompt/releases/download/v0.6.2/VoicePrompt-Setup-0.6.2-x64.exe".into(), size: 3, sha256: format!("{:x}", Sha256::digest(b"abc")) }
    }

    #[test]
    fn semantic_versions_and_stable_channel() {
        assert!(is_newer("0.6.10", "0.6.9").unwrap());
        assert!(!is_newer("0.6.2", "0.6.2").unwrap());
        assert!(!is_newer("0.6.1", "0.6.2").unwrap());
        assert!(is_newer("0.6.2-preview.1", "0.6.1").is_err());
        assert!(is_newer("0.6.2+build", "0.6.1").is_err());
    }

    #[test]
    fn release_urls_cannot_escape_the_repository_or_tag() {
        let good = manifest();
        validate_manifest(&good).unwrap();
        for url in [
            good.url.replace("https:", "http:"),
            good.url.replace("voiceprompt/", "other/"),
            good.url.replace("/v0.6.2/", "/v0.6.3/"),
            format!("{}?x=1", good.url),
            good.url.replace("github.com", "github.com.evil.example"),
        ] {
            let mut bad = good.clone();
            bad.url = url;
            assert!(validate_manifest(&bad).is_err());
        }
        let mut bad = good;
        bad.target = "windows-aarch64".into();
        assert!(validate_manifest(&bad).is_err());
    }

    #[test]
    fn missing_or_untrusted_signatures_are_rejected() {
        assert!(verify_envelope(b"{}", PUBLIC_KEY).is_err());
        let envelope = Envelope {
            payload: serde_json::to_string(&manifest()).unwrap(),
            signature: "invalid".into(),
        };
        assert!(verify_envelope(&serde_json::to_vec(&envelope).unwrap(), PUBLIC_KEY).is_err());
        assert!(verify_envelope(&vec![0; MAX_METADATA as usize + 1], PUBLIC_KEY).is_err());
    }

    #[test]
    fn checksum_rejects_modified_and_incomplete_installers() {
        let path =
            std::env::temp_dir().join(format!("voiceprompt-checksum-{}.bin", std::process::id()));
        std::fs::write(&path, b"abc").unwrap();
        drop(verify_installer(&path, &manifest()).unwrap());
        std::fs::write(&path, b"abd").unwrap();
        assert!(verify_installer(&path, &manifest()).is_err());
        std::fs::write(&path, b"ab").unwrap();
        assert!(verify_installer(&path, &manifest()).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
