# VoicePrompt 0.6.1 Beta 1

Public beta for Windows 10/11 x64. This is an early testing release.

## Download and install

Download **VoicePrompt-Setup-0.6.1-x64-unsigned-preview.exe** from this release.
Finish any recording and save your changes before installing. Install over the
existing VoicePrompt installation; saved settings, history, planner data and
cached models remain in place. Python and API keys are not required.

This beta uses the tested application build **0.6.1**. The app displays 0.6.1;
the **v0.6.1-beta.1** tag identifies its beta distribution status. If this exact
0.6.1 build is already installed, reinstalling is unnecessary.

## Included

- Local voice typing, transcript history, dictionary, tasks, timers and alarms.
- Settings controls for Check for updates and automatic stable-release checks.
- Update now with download progress/cancellation, followed by Restart to update
  or Later when a verified newer stable update is available.
- Native update verification and protection for active dictation, retained audio
  and unsaved forms before the update restart.

## Update channel and known limitations

- This beta is a manual download and is excluded from the stable update feed.
  Existing installations predating the updater need one manual installation.
- Stable update publishing is not active yet: the repository's two signing
  secrets and remaining stable acceptance gates still need to be completed.
  A source-code push alone does not distribute a packaged app update.
- A later stable version greater than 0.6.1 can use the updater once publishing
  is configured. A stable package with the same internal version needs a manual
  installation because the updater deliberately rejects equal versions.
- The desktop, engine and installer are unsigned by a Windows publisher.
  Windows may show trust warnings. Update cryptographic verification is separate
  from Windows publisher signing; neither the checksum nor this beta establishes
  SmartScreen reputation.
- Full Windows 10/11 hardware acceptance and a complete upgrade between two
  updater-enabled versions remain outstanding. This is not a production release.

## Validation and provenance

Application source: `9403d0b69fd8031ba99785acfa148096f573048a`.
The beta-publication commit changes documentation and the stable-tag filter;
application binaries are unchanged.

[Windows CI passed](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/runs/41087353075),
including Python/frontend/Rust checks, dependency audits, frozen-engine checks,
native UI/accessibility checks and installation/reinstallation/live uninstall.
The distributed installer was compiled locally from that application source and
independently checksum-checked. The attached signing audit records its unsigned
status and exact packaged executable hashes.

Installer SHA-256:

```text
c33e1745e67c4e9f83b247127cf33f11dc83bc719e4d7ed604a5efbf80993353
```

Speech recognition runs locally. Models download separately when prepared and
cached models work offline. Update checks contact GitHub without uploading audio,
transcripts or diagnostic logs. Optional contest services retain their existing
network behavior. Application code is MIT licensed; dependencies and models keep
their own terms and notices.
