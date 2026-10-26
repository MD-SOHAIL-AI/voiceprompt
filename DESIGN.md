---
name: VoicePrompt
description: A quiet reading desk for local Windows dictation and daily planning.
colors:
  background: "#F5F7F4"
  surface: "#FFFFFF"
  rail: "#EAF0E9"
  ink: "#243D31"
  muted: "#5C6D62"
  line: "#D6DFD5"
  accent: "#285D46"
  hover: "#1C4935"
  selected: "#DCEADC"
  danger: "#A43636"
rounded:
  field: "3px"
  button: "4px"
  group: "5px"
  floating-status: "8px"
---

# Design system: VoicePrompt

The existing light desk and sage rail remain the visual authority. The desktop now
uses PySide6/Qt Widgets, replacing the active Tk screens. Legacy Tk source and its
regression tests remain available as reference and are excluded from packaging.

## Typography and geometry

Use Windows Segoe UI, 11 pt body, 15 pt section headings, 25 pt page titles, and
48 pt focus-timer numerals. Text renders directly through Qt and scales with
Windows DPI; never rasterize text or enlarge a screenshot to implement scaling.
Headless Windows previews load installed Segoe UI fonts explicitly when Qt's
offscreen plugin cannot enumerate system fonts. Font files are not bundled.

The main window starts at 1120 × 790 device-independent pixels and fits the
available work area. Minimum size is 800 × 560. A 205-pixel sage rail contains
Dictation, History, Tasks, Focus timer, Alarms, Contests, and Settings. Content
insets are 30 left, 28 right, 24 top, and 14 bottom. Qt handles device scaling.

Pages use scrollable content; long forms wrap fields when necessary. Tables
stretch their columns, retain selection when refreshed, and use alternate paper
rows. Controls size to labels and preserve visible keyboard focus. Advanced
engine settings are collapsed initially. Do not make low-level model names part
of the basic dictation workflow.

## Interaction

First launch shows microphone selection, input checking, model preparation, and
practice instructions. The main Dictation page shows actual capture/recognition
state, elapsed recording time, model download progress, explicit errors, retry,
latest transcript, and Copy. Listening is shown only after capture starts.

The floating status window is opaque, border-defined, always on top, and does not
accept keyboard focus. It can be dragged and remembers its position. Recording
and processing states have written labels as well as color. Reminder cards also
avoid activation and defer display and sounds during dictation.

All Qt controls run on the main thread. Workers communicate through controller
state and queued callbacks. Closing the main window returns to the tray; Quit
ends the application and clears any recording held only in memory.

## Verification

Automated Qt tests exercise navigation, onboarding, settings, recovery, history,
and task-linked timers. Offscreen previews cover every page at 100% and 150%.
These previews do not establish physical microphone/hotkey operation, Windows
screen-reader behavior, or approval at every supported display scale; the
release checklist includes those native checks.
