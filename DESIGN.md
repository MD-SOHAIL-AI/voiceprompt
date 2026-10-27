---
name: "VoicePrompt"
description: "A compact local voice utility in forest charcoal and mint."
colors:
  background: "#131b18"
  rail: "#1a2621"
  surface: "#182320"
  input: "#141e1a"
  text: "#edf3ef"
  muted: "#a4b9aa"
  accent: "#8bd0af"
  amber: "#efbf63"
  danger: "#eba9a0"
  processing: "#a7bac9"
  border: "#35493b"
  button-border: "#506355"
typography:
  display:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "68px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.18
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
  transcript:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.5
  island-display:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  compact-label:
    fontFamily: "Encode Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  key: "4px"
  field: "5px"
  control: "6px"
  panel: "7px"
  dialog: "10px"
  peek: "16px"
  island: "18px"
  switch: "20px"
spacing:
  compact: "6px"
  small: "8px"
  control-gap: "10px"
  medium: "12px"
  large: "16px"
  panel: "20px"
  dialog: "24px"
  focus: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#10271b"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-default:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-danger:
    backgroundColor: "#7a3535"
    textColor: "#fff"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "#a0ddbf"
  field:
    backgroundColor: "{colors.input}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  navigation-selected:
    backgroundColor: "#294237"
    textColor: "#f0f7f2"
    rounded: "{rounded.control}"
    padding: "10px 14px 10px 13px"
  platform-tag:
    backgroundColor: "#203829"
    textColor: "#d8e7dc"
    rounded: "{rounded.field}"
    padding: "5px 7px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "20px"
  island-capsule:
    backgroundColor: "#0f1b18"
    textColor: "#e5f0e8"
    rounded: "{rounded.island}"
    padding: "0 11px"
    width: "112px"
    height: "32px"
---

# Design System: VoicePrompt

## Overview

**Creative North Star: "The compact voice utility"**

Forest-charcoal surfaces and mint actions make a quiet working canvas for local dictation and daily planning. Fine borders, readable lettering, and restrained amber reminders keep operational state easy to find. Controls are crisp and compact; content supplies the hierarchy without decorative imagery.

The approved replacement world is implemented in Tauri 2, React 19, and TypeScript. This document records `desktop/src/tokens.css`, `styles.css`, and the implemented components and pages. It supersedes the earlier light Qt design document. The selected composition remains in `.impeccable/surface-brief.md` and the approved mockups; implementation values govern this system.

**Key Characteristics:**

- Forest surfaces separated by fine borders and small tonal changes.
- Mint primary actions, progress, and keyboard focus; amber reminder emphasis.
- Locally bundled Encode Sans, sentence-case labels, and tabular countdowns.
- Seven visible tools in a labeled rail and a separate contextual island.
- Semantic controls, code-drawn SVG icons, and live waveform bars.

## Colors

The palette is a dark forest neutral family with one mint action accent and restrained colors for reminders and operational state. The frontmatter preserves the canonical CSS hex values.

### Primary

- **Mint:** `accent` marks primary buttons, links, waveform bars, progress, selection, and visible keyboard focus. Primary button text uses dark forest ink.

### Secondary

- **Reminder amber:** `amber` marks pending counts, alarm icons, and time-sensitive reminder details. It does not replace the mint action color.

### Neutral

- **Forest charcoal:** `background` is the workspace; `rail` is the slightly lighter navigation field; `surface` contains working groups; `input` recesses editable fields.
- **Light leaf:** `text` is the default text. `muted` supports dates, hints, secondary status, and empty-state explanations.
- **Forest strokes:** `border` separates groups and rows; `button-border` gives interactive fields and secondary actions a stronger edge.

### Operational state

- **Soft coral:** `danger` marks error status. Error notices and destructive buttons have dedicated darker backgrounds in their component styles.
- **Cool slate:** `processing` marks preparing and recognition state. Written labels accompany every recording state; color alone is insufficient.

### Named Rules

**The State Has Words Rule.** Keep recording, processing, error, and reminder meaning in visible text or accessible names alongside color and icons.

## Typography

**Display Font:** Encode Sans, with Segoe UI, system-ui, and sans-serif fallbacks.
**Body Font:** The same family throughout. The variable TrueType font is bundled at `desktop/src/assets/fonts/EncodeSans.ttf`, declared for weights 100–900 with `font-display: swap` and `font-synthesis: none`.

**Character:** A single clear sans family keeps the small utility coherent. Large countdowns use tabular numerals rather than a separate display or monospace face. The hierarchy is observed, not a fixed-ratio type scale.

### Hierarchy

- **Display:** The large mint focus countdown. Use the `display` role; numerals have `font-variant-numeric: tabular-nums`.
- **Headline:** Page titles use `headline`; the narrow preview reduces them to 26px. Do not introduce a decorative display face.
- **Title:** Section headings use `title`. Settings sections use 18px; the focus activity and dialog heading use 20px. Subheadings use 13px at weight 600.
- **Body:** Root text uses 14px at weight 400. The `body` line height applies to paragraphs. History transcripts use 15px; the latest transcript uses its dedicated larger role and preserves whitespace.
- **Label:** Main buttons use `label`, with primary buttons at weight 600. Field labels use 13px. Hints and metadata use 12px; island controls use 11px, with denser notification actions at 10px.
- **Island display:** The expanded island countdown uses `island-display`. Capsule text uses 12px; small badges use 9px.

### Named Rules

**The One Family Rule.** Use bundled Encode Sans for titles, controls, and numerals; apply tabular figures to durations and counts instead of changing font.

## Layout

The main native window starts at 1120 × 790 logical pixels and has an 800 × 560 minimum. The actual desktop grid has a 198px rail, a flexible workspace, and a 28px titlebar over the workspace. The workspace scrolls independently, with insets of 51px top, 22px sides, and 24px bottom. Its section container caps at 1400px. The rail has a full-height vertical navigation list; Settings sits at its bottom.

Spacing uses small, purpose-specific steps rather than a strict universal grid. Main panels use the `panel` inset; dialogs use `dialog`; field pairs use a 20px column gap. Forms are normally two columns, with three-column Pomodoro details. Lists use fine row separators and wrapping text. Latest transcript content has a 34vh height cap and its own scroll area.

The source also supports bounded browser previews: at 1020px controls and contest rows tighten; at 800px the rail becomes 170px, recording controls stack, and three-column forms become two; at 540px the rail becomes a 58px icon rail, forms become one column, and tables scroll horizontally. These preview breakpoints do not change the native main window's minimum size.

The separate island window is **112 × 32 logical pixels collapsed**, **280 × 96 for a reminder peek**, and **at most 320 × 400 expanded**. Native sizing matches these visible footprints and clamps expansion to available monitor work area. The expanded shell uses a header, three tabs, a scrolling body, and a fixed footer action. Focus shows the countdown, Pause/Resume, End session, quick presets, and the next alarm without hiding the footer. Its body can scroll when custom fields or longer content require space.

## Elevation & Depth

The resting workspace is flat: tonal surfaces and one-pixel borders establish depth. Shadows are reserved for transient dialogs and feedback. The native island has no OS shadow; its opaque forest body and border establish its outline.

### Shadow Vocabulary

- **Dialog:** `0 12px 36px #0008`, with a `#0009` backdrop.
- **Main toast:** `0 8px 24px #0006`.
- **Island toast:** `0 4px 12px #0006`.

### Named Rules

**The Bordered Surface Rule.** Separate resting groups with tonal fills and fine strokes; use the recorded shadows for transient layers.

## Shapes

Controls have modest roundness: fields and segmented tabs use `field`, buttons and navigation use `control`, and panels and table frames use `panel`. Dialogs use the larger `dialog` radius. The island is a distinct capsule and rounded panel using `island`; reminder peeks use `peek`. Switch tracks are fully rounded. Status dots, progress rings, and count badges retain their functional circular or pill shapes. Keep waveform bars as narrow rounded rectangles in SVG.

## Components

### Buttons

Compact, explicit actions with written labels and optional outline icons.

- **Default:** A forest surface, stronger border, and light text; minimum height 38px, an 8px icon gap, and the frontmatter padding.
- **Primary:** Mint fill and dark text at weight 600. Hover brightens the mint.
- **Ghost:** Transparent fill and border at rest; the standard hover gives it a forest fill and stronger stroke. Icon-only actions have accessible names.
- **Danger:** Dark red fill, red border, and white text. Confirmation dialogs name the operation and provide a cancel action. The implemented shared hover changes non-primary buttons to the standard forest hover treatment.
- **Focus / disabled:** Every keyboard-focusable control uses a 2px mint outline with a 3px offset; fields use a 1px offset. Disabled buttons and fields use opacity 0.58 and the native disabled attribute. Do not infer an unimplemented pressed animation.

### Chips

Platform tags are static source labels, with a dark green fill, fine stroke, 11px text, and small field corners. Amber count badges communicate pending reminders; counts above nine display `9+`. These are labels, not filter buttons.

### Cards / Containers

Working panels use the shared surface, fine border, panel corners, and panel inset. Tasks use a real table with row actions and completion buttons. History, alarms, contests, and notifications use separated rows rather than nested cards. Empty states use a short title and muted explanation capped at 45ch. Dialogs use Radix Dialog with a title, optional description, close control, and scrollable content bounded by the viewport.

### Inputs / Fields

Recessed forest fields use stronger strokes, field corners, and 10px × 12px padding. Main inputs and selects are at least 39px high. Visible labels wrap their controls; hints appear beneath. Textareas resize vertically. Search and microphone fields place SVG icons inside their left inset. Native required, numeric, and date/time constraints remain meaningful. The switch is a checkbox with a 32 × 19px track, a 13px thumb, and a 13px checked translation; its label stays attached to the input.

### Navigation

Seven tools remain available: Dictation, History, Tasks, Focus timer, Alarms, Contests, and Settings. Desktop items pair 20px outline icons with 14px labels. The selected item has a lighter forest fill and a 2px mint left edge, with `aria-current="page"`. Hover changes fill and text. The narrow browser preview hides visible text; the native supported width retains labeled navigation.

### Dictation state and waveform

The recording panel pairs a written status, status dot, elapsed/max time, live SVG waveform, shortcut instructions, microphone selector, and state-appropriate action. The waveform is an accessible image labeled as live or inactive; actual input supplies native bars. Preparation and recognition show progress and detail; errors use an alert with retry/discard when retained audio is available. Completed text remains selectable, focusable, scrollable, and copyable. Success and copy fallback appear in words.

### Contextual island

The compact island switches among recording, preparing/finishing, error, focus countdown, next-alarm countdown, and pending reminders. Its accessible name carries the full state. Click expands it; a movement threshold begins native dragging. Collapsed and peek windows are non-focusable; expansion is focusable, and loss of focus or Escape collapses it unless an alarm editor is open. Focus, Alarms, and Notifications form a semantic tablist with selected state, linked panels, and Arrow, Home, and End navigation. The Focus tab includes the next alarm's label, time, and enable switch. Notifications expose Snooze, Dismiss, and relevant Open actions.

Reminder peeks last eight seconds and are deferred during dictation. Successful insertion feedback lasts 900ms. The island resizes over 180ms with `cubic-bezier(0.16, 1, 0.3, 1)`; waveform bars respond over 75ms ease-out; the switch thumb moves over 130ms ease-out; loading icons rotate over one second. `prefers-reduced-motion: reduce` reduces animation and transition duration to 0.001ms, one animation iteration, and automatic scrolling.

### Accessibility and evidence limits

Implemented support includes visible focus, labels and accessible names, native button/input semantics, status and alert regions, semantic tabs, and Radix dialogs. Browser screenshots cover all seven pages, bounded widths, and island Focus and Notifications. The finish reviewer resolved the three material UI findings: the next alarm is visible, the palette matches the selected world, and the idle focus eyebrow is removed; bounded fix verification found no visible regressions. No physical microphone, DPI, or screen-reader validation is claimed.

This design record is not full workflow acceptance. The review disposition remains `fix`: the user explicitly waived the extra component/code-rendering approval checkpoint, and no further approval is required for authorized implementation or shipping after CI. That waiver is not a component-review receipt; the mechanical phase record remains open at `plates`, despite zero shipping raster assets. Native compilation, Rust checks, frozen smoke, and the real engine bridge passed CI on an earlier commit; native CDP automation remains pending repair.

## Do's and Don'ts

### Do:

- **Do** use forest tonal layers and fine borders to group content.
- **Do** keep mint actions and focus distinct from amber reminder emphasis.
- **Do** use bundled Encode Sans and tabular figures for countdowns.
- **Do** pair operational color and icons with written state or accessible names.
- **Do** preserve the island's visible native footprint and scroll its expanded body.
- **Do** keep reminders quiet while dictation is active and expose pending items afterward.

### Don't:

- **Don't** inherit the superseded light Qt palette or Segoe-only typography.
- **Don't** replace semantic controls, text, icons, or waveforms with raster screenshots.
- **Don't** add decorative eyebrows above working headings or idle focus content.
- **Don't** use ambient shadows on every resting panel.
- **Don't** treat preview screenshots as proof of physical microphone, DPI, or screen-reader behavior.
