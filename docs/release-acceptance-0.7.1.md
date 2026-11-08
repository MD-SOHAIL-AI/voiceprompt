# VoicePrompt 0.7.1 release record

Prepared on 8 November 2026 following the maintainer's request to ship the latest
changes through the in-app update channel. This promotes the 0.7.1 RC 1 source
to version 0.7.1; application behavior is unchanged apart from release identity.
The previous [candidate acceptance record](release-acceptance-0.7.1-rc.1.md)
remains historical evidence, rather than proof of a new stable package.

## Required publication checks

The matching `v0.7.1` tag must refer to main. The existing stable workflow rebuilds
the app, reruns all automated release checks, signs metadata with the existing
update key, tests installation and upgrade from 0.6.3, and retains its evidence
for 90 days. Its production environment review remains required. Installer and
metadata downloads must independently match and pass native signature verification
before the draft becomes the latest stable release. A prepared source commit or
green main build alone does not mean that users can download the update.

Track the exact source, job results, installer checksum and hosted verification
in the [stable workflow](https://github.com/MD-SOHAIL-AI/voiceprompt/actions/workflows/release.yml)
and [release assets](https://github.com/MD-SOHAIL-AI/voiceprompt/releases/tag/v0.7.1).

## Outstanding device acceptance

Physical microphone/hotkey trials, the Edge/VS Code destination matrix and focus
changes, normal-user clean Windows 10/11 lifecycle, screen readers and complete
DPI trials remain unverified. Neither this release request nor passing automated
checks changes those results to passed. Windows publisher signing remains deferred;
the update channel authenticates packages with its existing cryptographic key.

The maintainer's production review decides distribution with these documented
limits. No release protection, signing check, hosted-byte verification or required
automated check is disabled for this release.
