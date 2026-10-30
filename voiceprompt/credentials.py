"""Retire credentials belonging to the removed cloud-cleanup feature."""
import os


def _backend():
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def retire_cloud_credentials() -> str:
    if os.name != "nt" or os.environ.get("VOICEPROMPT_ACCEPTANCE_DIR"):
        return ""
    try:
        vault = _backend()
        for provider in ("gemini", "openrouter"):
            if vault.get_password("VoicePrompt.Cleanup", provider):
                vault.delete_password("VoicePrompt.Cleanup", provider)
        return ""
    except Exception:
        return "Old cloud credentials could not be removed. Retry removal in Settings. Dictation remains local."
