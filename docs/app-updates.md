# In-app updates and free releases

VoicePrompt 0.6.1 adds Settings controls for **Check for updates**, **Update now**,
download progress/cancellation, and **Restart to update**. **Later** keeps the
download. Automatic checks run about 30 seconds after launch and every six hours
while enabled; failed automatic checks also wait six hours before retrying.
Only the installed Windows x64 app updates itself. Browser previews simulate the
flow; source builds, acceptance profiles and the legacy Qt app do not self-update.

Before restart, save or discard form changes and recover or discard retained
audio. The engine rejects updates during recording, recognition, pending paste,
or model work, then blocks new hotkey work during shutdown. VoicePrompt is briefly
unavailable while installing; alarms and reminders resume after reopening.

## One-time signing setup

The repository contains only `desktop/src-tauri/update-public-key.pub`. Its
private key must persist across releases. Never regenerate a shipping identity
for convenience: older installations would reject the replacement key.

After installing the pinned frontend dependencies, initialize an identity once:

```powershell
python scripts/release_updates.py init
```

An initialized identity is already present in this checkout. Its encrypted
private key is in ignored `.tools/update-signing/update.key`. The random password
is protected by machine DPAPI in `password.dpapi`. Directory permissions restrict
access to the real Windows profile owner, the current agent account, SYSTEM and
administrators, so an isolated agent account does not strand the identity.
Keep a secure backup. Before moving to another computer, export/re-encrypt the
password while the original machine is available. GitHub secrets cannot be read
back through its API, so they are not a substitute for an offline recovery backup.

Configure release automation through authenticated GitHub CLI:

```powershell
python scripts/release_updates.py init --github
```

This sets `VOICEPROMPT_UPDATE_PRIVATE_KEY` and `VOICEPROMPT_UPDATE_KEY_PASSWORD`
without printing values. The GitHub connector does not expose repository-secret
configuration, so this setup command uses `gh`. Protect main/release tags and
restrict publishing access to trusted maintainers. Secrets reach only the
tag-release build step; they are not passed to PR tests or artifacts.

## Publish a stable update

1. Increase the canonical version in `pyproject.toml` and synchronize Python,
   desktop package/lockfile, Cargo/lockfile, and Tauri versions. Run
   `python scripts/verify_versions.py`.
2. Add `docs/release-notes-VERSION.md`, run checks, and merge into main.
3. Push the matching stable version tag, such as `v0.6.1`.

`.github/workflows/release.yml` verifies tag/main ancestry, runs regressions,
builds the complete app, signs metadata, verifies it using the packaged native
app, checks the engine/native UI/installer, uploads a complete draft, then
publishes it as latest. Failed checks publish nothing. Ordinary main pushes/PRs
do not publish. Prereleases are excluded. Never replace published installers;
repair a faulty release with a higher version.

For an explicit local update-signed release:

```powershell
python scripts/build_update_release.py --notes docs/release-notes-0.6.1.md
```

The driver uses the established builder's unsigned packaging checks, then builds
the final stable installer and signs its metadata. The existing publisher-signed
entrypoint keeps its certificate gate. `--skip-build` only repackages an already
verified local stage and is never used by CI.

Existing users need one manual installation of this first updater-enabled build.
Subsequent stable releases support the complete in-app flow.

## Verification, data and recovery

Discovery uses the public repository's `releases/latest/download/latest.json`,
without a GitHub login or embedded token. Rust uses Windows HTTPS trust/proxy
settings and explicit GitHub asset-host redirects. No browser network, filesystem
or shell permissions are added. No user content or diagnostics are uploaded.

The metadata envelope has `payload` (an exact UTF-8 manifest string) and
`signature` (a Minisign signature over those bytes). The schema-1 manifest binds
app identity, stable channel, Windows x64 target, semantic version, notes,
publication date, exact repository/tag installer URL, byte size, and SHA-256.
Metadata is verified before accepting a version, and downloaded bytes are checked
again by the detached helper before installation. Sizes and network waits are bounded.

Only application files are replaced. Settings, dictionary, history, planner
SQLite, credentials and model caches remain outside the installation. The current
startup choice is preserved. A package-file inventory permits obsolete file
cleanup without recursive deletion or following directory junctions.

The helper runs in `%LOCALAPPDATA%/VoicePrompt/updates`, verifies the running
parent's location, waits for exit, installs to that same folder and reopens the app.
Download failures leave the app running. Installer failures retain the installer
and local log for retry/manual repair. No Windows reboot is forced, and there is
no automatic rollback after a partial installation.

## Cost and Windows publisher signing

Use standard GitHub runners for the public repository and GitHub Releases for
installer hosting. Each release asset stays below 2 GiB. Routine CI omits large
packaged artifacts and uses short diagnostic retention. Keep caches within the
included allowance and configure an account billing budget that stops paid usage
at zero; a repository workflow cannot configure account billing settings.

Update signatures require no paid service. They establish authenticity relative
to the installed app's public key, independently of Windows Authenticode and
SmartScreen reputation. Windows can still show trust warnings. `.signing.json`
honestly records unsigned Windows binaries; `.update-signing.json` records
successful native update verification. Neither claims SmartScreen approval.

References: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
and [Minisign](https://jedisct1.github.io/minisign/).

## Verification and clean-machine acceptance

Automated checks include the Python suite and engine bridge, Rust trust/download
tests, frontend tests/build, and `node desktop/scripts/verify-updates.cjs` for the
explicit browser sample flow. The release workflow additionally requires frozen
application smoke, native WebView, and installation/uninstallation checks.
Browser sample checks do not prove native installation.

Before broad distribution, verify on Windows 10 and 11 in clean user accounts:

1. Install 0.6.1 manually. Create settings/dictionary changes, history, tasks,
   a timer, alarms, and a cached speech model. Test startup enabled and disabled.
2. Build a signed higher-version candidate. On the test machine, stage its
   signed `latest.json` as `%LOCALAPPDATA%/VoicePrompt/updates/pending.json` and
   its installer as `installer.exe`, then reopen the older installed app and
   choose Update now to verify the staged bytes without another download.
   This tests the handoff before publishing the candidate to everyone.
3. Verify Restart to update refuses active recording, recovery audio and unsaved
   forms. Then finish/save/discard deliberately, restart to update, and confirm
   the new version, all saved data, startup choices, model reuse and uninstall.
4. Verify corrupted metadata/installers, insufficient disk space, an interrupted
   download, installer failure, and a cancelled/retried operation. Preserve
   repair logs and confirm no Windows reboot occurs automatically.
5. After publication, independently verify Check for updates discovers the public
   stable feed. Drafts/prereleases must not replace the stable channel.

This development environment passed source/frozen engine, signing, browser and
unit checks. Native WebView startup is denied by its Windows sandbox, so full
native smoke and in-place upgrade acceptance must run in a normal Windows session
or the release workflow. Release gates remain mandatory.
