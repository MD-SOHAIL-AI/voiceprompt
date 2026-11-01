# Windows signing and SmartScreen

The 0.5.1 preview and the existing local 0.5.2 repair installer are unsigned.
Their desktop and speech-engine executables are also unsigned. Windows can show
the **Windows protected your PC** message before Setup starts. Changing the app
code, filename, icon, or installer permissions does not establish publisher trust.

Code signing verifies the publisher and protects the signed bytes. SmartScreen
also evaluates download reputation. A newly signed installer can still show the
warning, including with an EV certificate. Self-signed certificates do not solve
public distribution. See [Microsoft's SmartScreen guidance](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation).

## Set up a publisher identity

The account owner must complete the provider's identity checks. No signing
certificate is currently configured on this build machine. Do not put private
keys, certificate passwords, account tokens, or identity documents in GitHub,
this repository, or release artifacts.

For this MIT-licensed project, investigate [SignPath Foundation's free open-source
program](https://signpath.org/apply) before purchasing a certificate. Approval is
subject to their [conditions](https://signpath.org/terms), including license review,
MFA, named signing approvers, a published signing/privacy policy, and an approved
build/signing pipeline. The Foundation is the certificate publisher. Application
details that can be prepared from this repository:

- Project: VoicePrompt, local Windows voice typing and daily focus tools.
- Source: https://github.com/MD-SOHAIL-AI/voiceprompt
- Downloads: https://github.com/MD-SOHAIL-AI/voiceprompt/releases
- Application license: MIT; dependencies and model weights have their own terms
  listed in `THIRD_PARTY_NOTICES.md` and the packaged license files.
- Build: Windows x64, Tauri 2 desktop shell, PyInstaller speech engine, Inno Setup.
- Signing targets: `VoicePrompt.exe`, `VoicePromptEngine.exe`, Setup, and its
  embedded uninstaller/temporary Setup copies.
- Privacy: local speech processing; optional cloud transcript cleanup and contest
  services are documented in the README. Review the full network behavior before
  submitting a signing-policy declaration.

The owner must supply contact information, confirm maintainers/reviewers/approvers,
and accept provider terms. After approval, connect the provider's approved CI
pipeline and verify its returned artifacts. This repository does **not** claim an
active SignPath subscription or include a configured SignPath integration; the
local signing command below uses a certificate accessible through Windows.

For releases under your own publisher name, obtain a publicly trusted code-signing
certificate from a CA, with its required hardware token or cloud signing provider.
Install the provider's software so the certificate and private-key provider appear
in the Windows Personal (`My`) store. Identity verification and provider fees are
handled with the provider. Microsoft documents the [available signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options),
including geographic limits on Azure Artifact Signing. Verify eligibility before
creating a paid account; individual developers in India are currently outside
Azure Artifact Signing's supported individual regions.

If the requirement is to avoid this SmartScreen download warning from the first
installation, pursue Microsoft Store distribution. The MSIX route requires
packaging and Store certification; Microsoft signs approved MSIX packages.
Uploading the existing unsigned EXE to the Store is insufficient. This change
does not create a Store package or listing.

## Build with an installed signing certificate

List available signing identities without exporting private keys:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Select-Object Subject, Thumbprint, NotAfter, HasPrivateKey
```

Connect the certificate's token/signing provider, install the Windows SDK signing
tools, then use its actual thumbprint:

```powershell
.\scripts\build_desktop.ps1 -SignThumbprint 'YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT'
```

For a machine-store certificate add `-CertificateStore LocalMachine`. Supply
`-SignToolPath 'C:\path\to\signtool.exe'` if SDK auto-discovery does not find it.
`build_windows.ps1` accepts the same signing options.

The build rejects missing, expired, self-signed, or unsuitable signing identities.
It signs the staged desktop and speech engine with SHA-256 and RFC 3161 timestamps,
then verifies their signatures using Windows and `signtool verify /pa /all /tw`.
Inno's signing callback signs Setup, its temporary copies and embedded uninstaller.
The build verifies the installer and generated uninstaller before generating the
final checksum. The staged manifest records the desktop's hash **after signing**.

Outputs are `release/VoicePrompt-Setup-VERSION-x64.exe`, `.exe.sha256`, and
`.exe.signing.json`. The JSON records actual publisher identities, timestamps,
signature results, and SHA-256 hashes. Signature verification does not establish
SmartScreen reputation, and the report explicitly says this.

Before distribution, independently repeat the checks on the final package:

```powershell
.\scripts\check_windows_signing.ps1 -ExpectedThumbprint 'YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT'
# In a clean Windows account or VM:
.\scripts\check_installer.ps1
```

The installer check verifies the installed desktop, engine, and `unins000.exe`
against the installer's signing identity. Complete the other
[release acceptance gates](production-release-gates.md) and test the downloaded
artifact on a clean Windows laptop. Do not change signed files afterward.

## Explicit unsigned tests

Developer and CI testing can use:

```powershell
.\scripts\build_desktop.ps1 -AllowUnsignedPreview
.\scripts\check_windows_signing.ps1 -AllowUnsignedPreview
.\scripts\check_installer.ps1 -AllowUnsignedPreview
```

These installers have an `-unsigned-preview.exe` suffix, cannot be marked
`signing_verified` by the signing audit, and can still trigger SmartScreen. The signed
and unsigned flags are mutually exclusive. Routine CI only produces unsigned
test artifacts; it does not sign or publish releases. Direct Inno compilation
also requires an explicit signed or unsigned build mode.

## For the existing installer on a family laptop

Check the SHA-256 against the release checksum and verify the download's source.
An unsigned preview has no verified publisher identity. Only if you trust that
exact preview, **More info → Run anyway** can allow this individual installation
when Windows policy permits it. This is a temporary user decision, not a signing
fix. Keep SmartScreen and antivirus enabled; do not add a new trusted root or
disable Windows protections for VoicePrompt.

Already downloaded copies remain unsigned. A signed replacement must be built,
verified, and downloaded separately. Do not overwrite a published release's
artifacts; use a new release identifier.
