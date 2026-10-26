"""Provider keys use Windows Credential Manager, never the settings file."""
def _backend():
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def get_key(provider):
    try:
        return _backend().get_password("VoicePrompt.Cleanup", provider) or ""
    except Exception:
        return ""


def save_key(provider, value):
    if provider not in {"openrouter", "gemini"}:
        raise ValueError("Select a supported cleanup provider.")
    try:
        _backend().set_password("VoicePrompt.Cleanup", provider, value.strip())
    except Exception:
        raise RuntimeError("Windows credential storage is unavailable. Your key was not saved.") from None
