# Build from the repository root with python -m PyInstaller packaging/VoicePrompt.spec.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / 'voiceprompt' / 'assets'), 'voiceprompt/assets'),
         (str(root / 'voiceprompt' / 'release.json'), 'voiceprompt'),
         (str(root / 'LICENSE'), '.'), (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
if (root / 'build' / 'licenses').exists():
    datas.append((str(root / 'build' / 'licenses'), 'licenses'))
binaries = []
for package in ('faster_whisper', 'ctranslate2', 'moonshine_voice', 'sherpa_onnx', 'soxr', 'tzdata'):
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)
for distribution in ('faster-whisper', 'ctranslate2', 'moonshine-voice', 'sherpa-onnx', 'sherpa-onnx-core',
                     'huggingface-hub', 'google-genai', 'keyring', 'PySide6-Essentials', 'shiboken6', 'numpy', 'soxr'):
    datas += copy_metadata(distribution)

# Only use pyrnnoise's native DLL, never its audio/plotting Python imports.
from importlib.util import find_spec
noise = find_spec('pyrnnoise')
if noise:
    for library in Path(noise.origin).parent.rglob('*.dll'):
        binaries.append((str(library), 'pyrnnoise'))

a = Analysis([str(root / 'VoicePrompt.pyw')], pathex=[str(root)],
    binaries=binaries, datas=datas,
    hiddenimports=['voiceprompt.desktop', 'voiceprompt.backend_process', 'voiceprompt.smoke',
                   'voiceprompt.transcriber', 'voiceprompt.parakeet', 'voiceprompt.nemotron',
                   'google.genai', 'moonshine_voice', 'sherpa_onnx',
                   'keyring.backends.Windows', 'pynput.keyboard._win32', 'pynput.mouse._win32',
                   '_cffi_backend'],
    excludes=['tkinter', 'voiceprompt.planner_ui', 'voiceprompt.settings_ui', 'voiceprompt.theme',
              'voiceprompt.evaluate', 'pyautogui', 'pystray', 'matplotlib', 'audiolab',
              'torch', 'tensorflow', 'transformers', 'scipy', 'IPython', 'pytest'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VoicePrompt', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'build' / 'VoicePrompt.ico') if (root / 'build' / 'VoicePrompt.ico').exists() else None,
          version=str(root / 'packaging' / 'version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VoicePrompt')
