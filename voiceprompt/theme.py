"""VoicePrompt's opaque, DPI-scaled Windows visual system."""
from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk


BACKGROUND = "#F5F7F4"
SURFACE = "#FFFFFF"
RAIL = "#EAF0E9"
INK = "#243D31"
MUTED = "#5C6D62"
LINE = "#D6DFD5"
ACCENT = "#285D46"
HOVER = "#1C4935"
SELECTED = "#DCEADC"
DANGER = "#A43636"


def scale_for(widget) -> float:
    return max(1.0, float(widget.winfo_fpixels("1i")) / 96)


def pixels(widget, value: float) -> int:
    return round(value * scale_for(widget))


def install_theme(root) -> None:
    if getattr(root, "_voiceprompt_theme", False):
        return
    root._voiceprompt_theme = True
    root.configure(background=BACKGROUND)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        font.nametofont(name, root=root).configure(family="Segoe UI", size=11)
    root.option_add("*Font", "TkDefaultFont")
    root.option_add("*Listbox.background", SURFACE)
    root.option_add("*Listbox.foreground", INK)
    root.option_add("*Listbox.selectBackground", SELECTED)
    root.option_add("*Listbox.selectForeground", INK)
    p = lambda value: pixels(root, value)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 11), foreground=INK, background=BACKGROUND)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Rail.TFrame", background=RAIL)
    style.configure("TLabel", background=BACKGROUND, foreground=INK)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Surface.TLabel", background=SURFACE)
    style.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
    style.configure("Heading.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("RailTitle.TLabel", background=RAIL, font=("Segoe UI", 17, "bold"))
    style.configure("RailMuted.TLabel", background=RAIL, foreground=MUTED, font=("Segoe UI", 10))
    style.configure("Timer.TLabel", font=("Segoe UI", 52, "bold"), background=SURFACE)
    style.configure("TButton", width=0, padding=(p(13), p(9)), background=SURFACE, foreground=INK,
                    borderwidth=1, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                    focuscolor=ACCENT, focusthickness=2)
    style.map("TButton", background=[("disabled", BACKGROUND), ("pressed", SELECTED), ("active", RAIL)],
              foreground=[("disabled", MUTED)], bordercolor=[("focus", ACCENT)])
    style.configure("Primary.TButton", background=ACCENT, foreground="#FFFFFF", bordercolor=ACCENT,
                    lightcolor=ACCENT, darkcolor=ACCENT, font=("Segoe UI", 11, "bold"))
    style.map("Primary.TButton", background=[("disabled", LINE), ("active", HOVER), ("pressed", HOVER)],
              foreground=[("disabled", MUTED), ("!disabled", "#FFFFFF")])
    style.configure("Quiet.TButton", borderwidth=0, background=BACKGROUND)
    style.configure("Danger.TButton", foreground=DANGER)
    style.configure("Nav.TButton", anchor="w", padding=(p(16), p(13)), background=RAIL, borderwidth=0,
                    font=("Segoe UI", 11), focuscolor=ACCENT)
    style.map("Nav.TButton", background=[("active", SELECTED), ("pressed", SELECTED)])
    style.configure("SelectedNav.TButton", anchor="w", padding=(p(16), p(13)), background=SURFACE,
                    foreground=ACCENT, borderwidth=0, font=("Segoe UI", 11, "bold"), focuscolor=ACCENT)
    style.map("SelectedNav.TButton", background=[("active", SURFACE)])
    for control in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(control, fieldbackground=SURFACE, foreground=INK, padding=p(8),
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowsize=p(12))
        style.map(control, fieldbackground=[("readonly", SURFACE), ("disabled", BACKGROUND)],
                  bordercolor=[("focus", ACCENT)], selectbackground=[("!disabled", SELECTED)],
                  selectforeground=[("!disabled", INK)])
    style.configure("TCheckbutton", background=BACKGROUND, foreground=INK, padding=(0, p(5)))
    style.map("TCheckbutton", background=[("active", BACKGROUND)], indicatorbackground=[("selected", ACCENT)])
    style.configure("TRadiobutton", background=BACKGROUND, padding=(0, p(5)))
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                    rowheight=p(43), borderwidth=0, font=("Segoe UI", 11))
    style.configure("Treeview.Heading", background=BACKGROUND, foreground=MUTED, borderwidth=0,
                    font=("Segoe UI", 10, "bold"), padding=(p(12), p(11)))
    style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", INK)])
    style.map("Treeview.Heading", background=[("active", RAIL)])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=(0, 0, 0, p(12)))
    style.configure("TNotebook.Tab", padding=(p(14), p(10)), background=RAIL)
    style.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", ACCENT)])
    style.layout("Workspace.TNotebook.Tab", [])
    style.configure("Workspace.TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=0)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=RAIL, borderwidth=0, thickness=p(5))
    style.configure("Vertical.TScrollbar", background=LINE, troughcolor=BACKGROUND, borderwidth=0, arrowsize=p(10))
    style.configure("TSeparator", background=LINE)


def fit_window(window, width=1120, height=760, minimum=(800, 560)):
    p = lambda value: pixels(window, value)
    available_w, available_h = window.winfo_screenwidth() - p(40), window.winfo_screenheight() - p(80)
    window.geometry(f"{min(p(width), available_w)}x{min(p(height), available_h)}")
    window.minsize(min(p(minimum[0]), available_w), min(p(minimum[1]), available_h))


class ScrollablePage(ttk.Frame):
    """Forms scroll inside their page rather than growing beyond the screen."""

    def __init__(self, parent, padding=0):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=BACKGROUND, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._body_id = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._body_id, width=e.width))
        # A per-window binding avoids interfering with other Tk interpreters or apps.
        self._top = self.winfo_toplevel()
        self._bindings = {
            "<MouseWheel>": self._top.bind("<MouseWheel>", self._wheel, add="+"),
            "<FocusIn>": self._top.bind("<FocusIn>", self._reveal_focus, add="+"),
            "<Prior>": self._top.bind("<Prior>", lambda e: self._page(e, -1), add="+"),
            "<Next>": self._top.bind("<Next>", lambda e: self._page(e, 1), add="+"),
        }
        self.bind("<Destroy>", self._destroyed, add="+")

    def _wheel(self, event):
        if self.winfo_ismapped() and str(event.widget).startswith(str(self)):
            self.canvas.yview_scroll(round(-event.delta / 120), "units")

    def _page(self, event, direction):
        if self.winfo_ismapped() and str(event.widget).startswith(str(self)):
            self.canvas.yview_scroll(direction, "pages")
            return "break"

    def _reveal_focus(self, event):
        if not self.winfo_ismapped() or not str(event.widget).startswith(str(self.body)):
            return
        top = event.widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        height = self.canvas.winfo_height()
        offset = top - 8 if top < 0 else bottom - height + 8 if bottom > height else 0
        if offset:
            target = max(0, self.canvas.canvasy(0) + offset)
            self.canvas.yview_moveto(target / max(1, self.body.winfo_height()))

    def _destroyed(self, event):
        if event.widget is self:
            try:
                for sequence, binding in self._bindings.items():
                    self._top.unbind(sequence, binding)
            except tk.TclError:
                pass
