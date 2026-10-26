# Third-party software and models

VoicePrompt's application code uses the MIT license. This does not relicense its
dependencies, native libraries, model weights, or bundled public warmup speech.

- Qt / PySide6 / Shiboken: LGPLv3 / GPLv3 / commercial terms as applicable.
  Only Qt Core, Gui, Widgets and their required runtime plugins are used.
  Qt libraries remain separate DLLs in the installed application. License texts
  and the installed distributions' notices accompany the binary release.
  Source: https://code.qt.io/pyside/pyside-setup.git and https://code.qt.io/qt/qtbase.git
  Qt licensing: https://doc.qt.io/qt-6/licensing.html
- PyInstaller: GPL with its bootloader exception; see the bundled license.
- faster-whisper, Whisper models, and CTranslate2: their upstream MIT licenses.
- ONNX Runtime and sherpa-onnx: their upstream MIT / Apache-2.0 licenses.
- Moonshine runtime and weights: their upstream runtime and model-specific terms.
- NVIDIA NeMo-Speech.cpp: Apache-2.0 plus its third-party notices. Downloaded
  runtime archives retain share/licenses/nemo-speech beside the native binaries.
- NVIDIA Nemotron model weights: NVIDIA Open Model License, separate from the
  runtime and application licenses. Model source and governing terms:
  https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b
- Parakeet model weights: see their model-specific terms at
  https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- RNNoise native library: BSD-3-Clause; the optional pyrnnoise distribution and
  all third-party components retain their respective licenses.
- NumPy, soxr, sounddevice/PortAudio, Pillow, pynput, keyring, and other Python
  dependencies retain their upstream licenses. Full installed license texts
  are collected under licenses/ in each packaged release.
- Public Nemotron warmup speech: VoiceArena, MonsoonASR Open ASR leaderboard,
  Indian English, sample 40631389_215_58_229_71, CC BY 4.0. Converted to 16 kHz
  mono PCM; speech content unchanged. See voiceprompt/assets/README.md.

Model files are downloaded from their providers and are not embedded in the
application installer. The Downloads screen identifies the selected engine;
provider model cards above and the runtime's retained notices govern those files.

You may replace the LGPL Qt DLLs with compatible builds and debug modifications
to those libraries; application terms do not prohibit that activity. This notice
does not remove any rights granted by the applicable third-party licenses.
