"""Progress for model downloads in the isolated worker, including Hugging Face."""
import time

_reporter = None


def report_progress(value):
    if _reporter is not None:
        _reporter(value)


def install_progress_reporting(report):
    global _reporter
    _reporter = report
    from tqdm.auto import tqdm
    import huggingface_hub

    class DownloadProgress(tqdm):
        def __init__(self, *args, **kwargs):
            self._last_report = 0
            kwargs["disable"] = False
            kwargs["file"] = open_null()
            self._sink = kwargs["file"]
            super().__init__(*args, **kwargs)
            self._report()

        def _report(self):
            now = time.monotonic()
            if now - self._last_report >= 0.15:
                self._last_report = now
                report({"phase": "Downloading model", "name": str(self.desc),
                        "completed": self.n, "total": self.total})

        def update(self, n=1):
            value = super().update(n)
            self._report()
            return value

        def close(self):
            if hasattr(self, "_sink"):
                super().close()
                self._sink.close()

    original_file = huggingface_hub.hf_hub_download
    original_snapshot = huggingface_hub.snapshot_download

    def file_download(*args, **kwargs):
        kwargs.setdefault("tqdm_class", DownloadProgress)
        return original_file(*args, **kwargs)

    def snapshot_download(*args, **kwargs):
        # faster-whisper explicitly supplies a disabled progress class.
        kwargs["tqdm_class"] = DownloadProgress
        return original_snapshot(*args, **kwargs)

    huggingface_hub.hf_hub_download = file_download
    huggingface_hub.snapshot_download = snapshot_download


def open_null():
    import os
    return open(os.devnull, "w", encoding="utf-8")
