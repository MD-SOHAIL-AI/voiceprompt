"""Thread-safe presentation adapters. Qt is created only by run(), on the main thread."""
import queue


class FloatingPill:
    def __init__(self, *, controller=None, **callbacks):
        self.controller = controller
        self.callbacks = callbacks
        self.events = queue.SimpleQueue()
        self.host = None
        self.status = "idle"

    def set_status(self, status):
        self.status = status

    def call(self, callback):
        self.events.put(callback)

    def show_page(self, name):
        self.call(lambda: self.host.show_page(name) if self.host else None)

    def run(self):
        from voiceprompt.desktop import DesktopHost
        self.host = DesktopHost(self.controller, self)
        self.host.run()

    def stop(self):
        self.call(lambda: self.host.stop() if self.host else None)


class TrayApp:
    def __init__(self, *, controller=None, **callbacks):
        self.controller = controller
        self.callbacks = callbacks

    def run_detached(self):
        pass

    def refresh(self):
        # The Qt main-thread timer reads controller snapshots.
        pass

    def open_settings(self):
        self.controller.pill.show_page("Settings")

    def stop(self):
        pass
